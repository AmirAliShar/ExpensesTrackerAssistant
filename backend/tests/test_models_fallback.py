import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.core.config import settings
from app.models.factory import (
    classify_model_error,
    ModelFactory,
    NonRetryableModelError,
    ainvoke_with_fallback,
)
from langchain_core.messages import HumanMessage, AIMessage


def test_model_candidates_order():
    """Verify primary model and Groq fallback candidate sequence."""
    candidates = settings.ALL_GROQ_MODELS
    assert "llama-3.1-8b-instant" in candidates
    assert "llama-3.3-70b-versatile" in candidates
    assert "openai/gpt-oss-120b" in candidates
    # Primary model is first
    assert candidates[0] == "llama-3.1-8b-instant"


def test_classify_model_error():
    """Verify error classification distinguishes retryable vs non-retryable errors."""
    # 401 Unauthorized -> non-retryable
    err_401 = Exception("Error code: 401 - {'error': {'message': 'Invalid API Key'}}")
    assert classify_model_error(err_401) == "non_retryable"

    # 400 Bad Request -> non-retryable
    err_400 = Exception("Error code: 400 - Bad request payload")
    assert classify_model_error(err_400) == "non_retryable"

    # 429 Rate Limit -> retryable
    err_429 = Exception("Error code: 429 - Rate limit reached for model llama-3.1-8b-instant")
    assert classify_model_error(err_429) == "retryable_rate_limit"

    # 503 Service Unavailable -> retryable
    err_503 = Exception("Error code: 503 - Service Unavailable")
    assert classify_model_error(err_503) == "retryable_server_error"


@pytest.mark.asyncio
async def test_non_retryable_error_fast_fails():
    """Verify 401 Authentication error immediately raises NonRetryableModelError without looping."""
    mock_chat = MagicMock()
    mock_chat.ainvoke = AsyncMock(side_effect=Exception("401 Invalid API Key"))

    with patch.object(ModelFactory, "get_groq_api_key", return_value="invalid_key"), \
         patch.object(ModelFactory, "create_chat_groq", return_value=mock_chat):

        with pytest.raises(NonRetryableModelError):
            await ModelFactory.ainvoke_with_fallback([HumanMessage(content="Hello")])

        # Verify it didn't endlessly loop
        assert mock_chat.ainvoke.call_count == 1


@pytest.mark.asyncio
async def test_retryable_error_falls_back_to_next_candidate():
    """Verify a 429 rate limit on candidate 1 triggers fallback to candidate 2."""
    call_counts = {}

    def mock_create(model_name, **kwargs):
        mock_instance = MagicMock()
        if model_name == "llama-3.1-8b-instant":
            mock_instance.ainvoke = AsyncMock(side_effect=Exception("429 Rate limit reached"))
        else:
            mock_instance.ainvoke = AsyncMock(return_value=AIMessage(content=f"Response from {model_name}"))
        return mock_instance

    with patch.object(ModelFactory, "get_groq_api_key", return_value="gsk_valid_key"), \
         patch.object(ModelFactory, "create_chat_groq", side_effect=mock_create), \
         patch.object(settings, "MODEL_MAX_RETRIES", 1), \
         patch("asyncio.sleep", AsyncMock()):  # Avoid sleep delays in unit test

        result = await ModelFactory.ainvoke_with_fallback([HumanMessage(content="What are my expenses?")])
        assert "Response from llama-3.3-70b-versatile" in result.content


@pytest.mark.asyncio
async def test_model_not_found_falls_back_to_next_candidate():
    """Verify 404 model_not_found skips retries and gracefully progresses to fallback candidate."""
    invoked_models = []

    def mock_create(model_name, **kwargs):
        mock_instance = MagicMock()
        if model_name == "llama-3.1-8b-instant":
            err_msg = "Error code: 404 - {'error': {'message': 'The model `llama-3.1-8b-instant` does not exist or you do not have access to it.', 'type': 'invalid_request_error', 'code': 'model_not_found'}}"
            mock_instance.ainvoke = AsyncMock(side_effect=Exception(err_msg))
        elif model_name == "llama-3.3-70b-versatile":
            err_msg = "Error code: 404 - {'error': {'message': 'The model `llama-3.3-70b-versatile` does not exist or you do not have access to it.', 'type': 'invalid_request_error', 'code': 'model_not_found'}}"
            mock_instance.ainvoke = AsyncMock(side_effect=Exception(err_msg))
        else:
            mock_instance.ainvoke = AsyncMock(return_value=AIMessage(content=f"Response from {model_name}"))
        
        async def record_invoke(*args, **kwargs):
            invoked_models.append(model_name)
            return await mock_instance.ainvoke(*args, **kwargs)

        mock_obj = MagicMock()
        mock_obj.ainvoke = record_invoke
        return mock_obj

    with patch.object(ModelFactory, "get_groq_api_key", return_value="gsk_valid_key"), \
         patch.object(ModelFactory, "create_chat_groq", side_effect=mock_create), \
         patch.object(settings, "MODEL_MAX_RETRIES", 1), \
         patch("asyncio.sleep", AsyncMock()):

        result = await ModelFactory.ainvoke_with_fallback([HumanMessage(content="Show my balance")])
        assert "Response from openai/gpt-oss-120b" in result.content
        # 404 should not retry candidate 1 multiple times: only 1 attempt per 404 candidate
        assert invoked_models.count("llama-3.1-8b-instant") == 1
        assert invoked_models.count("llama-3.3-70b-versatile") == 1
        assert "openai/gpt-oss-120b" in invoked_models
