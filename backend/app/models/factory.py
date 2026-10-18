import os
import time
import random
import asyncio
import logging
from typing import List, Optional, Any, Dict
from langchain_core.messages import BaseMessage
from langchain_groq import ChatGroq

from app.core.config import settings

logger = logging.getLogger("finpilot.models")


class NonRetryableModelError(Exception):
    """Raised when model returns non-retryable errors like 401 Unauthorized or bad requests."""
    pass


class RetryableModelError(Exception):
    """Raised when model encounters transient errors like 429 rate limit or 503 unavailable."""
    pass


def classify_model_error(error: Exception) -> str:
    """Classify model error into 'non_retryable', 'model_not_found', 'retryable_*', or 'unknown'."""
    err_str = str(error).lower()

    # Model not found or deprecated (404) - fast skip to next candidate model
    if "404" in err_str or "model_not_found" in err_str or "does not exist or you do not have access" in err_str:
        return "model_not_found"

    # Non-retryable authentication / API key failures
    if "401" in err_str or "unauthorized" in err_str or "invalid_api_key" in err_str or "api_key" in err_str:
        return "non_retryable"
    if "400" in err_str or "bad request" in err_str or "invalid_request" in err_str:
        return "non_retryable"

    # Retryable / rate limit / server error
    if "429" in err_str or "rate limit" in err_str or "tpm" in err_str or "rpm" in err_str:
        return "retryable_rate_limit"
    if "503" in err_str or "service unavailable" in err_str or "500" in err_str or "502" in err_str or "504" in err_str:
        return "retryable_server_error"
    if "timeout" in err_str or "connection error" in err_str or "connect" in err_str:
        return "retryable_network"

    return "unknown"


class ModelFactory:
    """
    Centralized model provider and dynamic fallback manager.
    Follows LangChain dynamic model selection patterns with exponential backoff & jitter.
    """

    @classmethod
    def get_groq_api_key(cls) -> Optional[str]:
        key = settings.GROQ_API_KEY
        if not key or key.strip().lower().startswith("your_") or key.strip() == "":
            return None
        return key.strip()

    @classmethod
    def is_configured(cls) -> bool:
        return cls.get_groq_api_key() is not None

    @classmethod
    def create_chat_groq(cls, model_name: str, temperature: float = 0.1) -> ChatGroq:
        api_key = cls.get_groq_api_key()
        if not api_key:
            raise NonRetryableModelError("GROQ_API_KEY is not configured in environment.")

        return ChatGroq(
            api_key=api_key,
            model=model_name,
            temperature=temperature,
            max_retries=1,  # We manage bounded retries explicitly with backoff & fallbacks
            timeout=float(settings.MODEL_TIMEOUT_SECONDS),
        )

    @classmethod
    def get_candidate_models(cls) -> List[str]:
        return settings.ALL_GROQ_MODELS

    @classmethod
    async def ainvoke_with_fallback(
        cls,
        messages: List[BaseMessage],
        temperature: float = 0.1,
        tools: Optional[List[Any]] = None,
    ) -> Any:
        """
        Execute chat invocation traversing candidate models with bounded retries and exponential backoff.
        Candidates: llama-3.1-8b-instant -> llama-3.3-70b-versatile -> openai/gpt-oss-120b.
        """
        if not cls.is_configured():
            raise NonRetryableModelError("GROQ_API_KEY is missing or invalid placeholder.")

        candidate_models = cls.get_candidate_models()
        last_error = None

        for model_idx, model_name in enumerate(candidate_models):
            logger.info(f"Attempting model candidate [{model_idx + 1}/{len(candidate_models)}]: '{model_name}'")

            try:
                chat_model = cls.create_chat_groq(model_name, temperature=temperature)
                if tools:
                    chat_model = chat_model.bind_tools(tools)

                # Attempt bounded retries for this specific model
                max_retries = settings.MODEL_MAX_RETRIES
                for attempt in range(max_retries + 1):
                    try:
                        response = await chat_model.ainvoke(messages)
                        logger.info(f"Successfully generated response with model '{model_name}'.")
                        return response
                    except Exception as exc:
                        last_error = exc
                        err_category = classify_model_error(exc)
                        logger.warning(
                            f"Model '{model_name}' attempt {attempt + 1}/{max_retries + 1} "
                            f"failed. Error category: {err_category}"
                        )

                        if err_category == "non_retryable":
                            err_msg_lower = str(exc).lower()
                            # Fast-fail provider entirely on authentication failure
                            if "401" in err_msg_lower or "unauthorized" in err_msg_lower or "api_key" in err_msg_lower:
                                logger.error(f"Authentication failure encountered for '{model_name}': {exc}")
                                raise NonRetryableModelError(str(exc)) from exc
                            # Otherwise non-retryable for this specific model; try next fallback candidate
                            logger.warning(f"Non-retryable error for '{model_name}': {exc}. Skipping to next candidate.")
                            break

                        if err_category == "model_not_found":
                            # Model not found or deprecated: immediately skip to next candidate without useless retries
                            logger.warning(
                                f"Model '{model_name}' not found or unavailable (404). Transitioning to next candidate."
                            )
                            break

                        if attempt < max_retries and err_category.startswith("retryable"):
                            backoff = (2 ** attempt) * 0.5 + random.uniform(0.1, 0.4)
                            logger.info(f"Applying backoff ({backoff:.2f}s) before retrying '{model_name}'...")
                            await asyncio.sleep(backoff)
                        else:
                            # Retries exhausted for this model, break to fallback candidate
                            break

                logger.warning(
                    f"Exhausted retries for candidate model '{model_name}'. "
                    f"Transitioning to next eligible fallback model..."
                )

            except NonRetryableModelError:
                raise
            except Exception as e:
                last_error = e
                logger.error(f"Error initializing or invoking candidate '{model_name}': {e}")
                continue

        # If all candidates fail
        final_msg = f"All configured Groq models failed. Last error: {last_error}"
        logger.error(final_msg)
        raise RuntimeError(final_msg)


def get_chat_model(temperature: float = 0.1) -> ChatGroq:
    """Helper to get primary configured ChatGroq instance."""
    return ModelFactory.create_chat_groq(settings.PRIMARY_CHAT_MODEL, temperature=temperature)


async def ainvoke_with_fallback(
    messages: List[BaseMessage],
    temperature: float = 0.1,
    tools: Optional[List[Any]] = None
) -> Any:
    return await ModelFactory.ainvoke_with_fallback(messages, temperature=temperature, tools=tools)
