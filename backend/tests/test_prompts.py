from app.core.config import settings
from app.agents.prompts.loader import get_prompt, get_all_prompts
from app.agents.prompts.defaults import (
    DEFAULT_FINANCE_SUPERVISOR_PROMPT,
    DEFAULT_EXPENSE_AGENT_PROMPT,
    DEFAULT_BUDGET_AGENT_PROMPT,
    DEFAULT_ANALYTICS_AGENT_PROMPT,
    DEFAULT_MEMORY_AGENT_PROMPT,
    DEFAULT_VOICE_AGENT_PROMPT,
)


def test_default_prompts_load_correctly():
    """Verify default prompts contain specialist role instructions."""
    all_prompts = get_all_prompts()
    assert "supervisor" in all_prompts
    assert "expense" in all_prompts
    assert "budget" in all_prompts
    assert "analytics" in all_prompts
    assert "memory" in all_prompts
    assert "voice" in all_prompts

    assert "Lead Financial Supervisor" in all_prompts["supervisor"]
    assert "Expense & Transaction Specialist" in all_prompts["expense"]
    assert "Budget & Spending Limit Specialist" in all_prompts["budget"]
    assert "Financial Analytics & Insights Specialist" in all_prompts["analytics"]
    assert "Personal Finance Memory Specialist" in all_prompts["memory"]
    assert "Voice Response Synthesizer" in all_prompts["voice"]


def test_environment_prompt_override():
    """Verify prompt loader respects environment variable override when enabled."""
    custom_supervisor_prompt = "Custom overridden supervisor prompt for enterprise audit."

    original_setting = settings.FINANCE_SUPERVISOR_PROMPT
    original_flag = settings.AGENT_PROMPTS_FROM_ENV

    try:
        settings.AGENT_PROMPTS_FROM_ENV = True
        settings.FINANCE_SUPERVISOR_PROMPT = custom_supervisor_prompt
        loaded_prompt = get_prompt("supervisor")
        assert loaded_prompt == custom_supervisor_prompt
    finally:
        settings.FINANCE_SUPERVISOR_PROMPT = original_setting
        settings.AGENT_PROMPTS_FROM_ENV = original_flag


def test_empty_environment_override_falls_back_to_safe_default():
    """Verify empty or None override safely reverts to default prompt."""
    original_setting = settings.EXPENSE_AGENT_PROMPT
    try:
        settings.AGENT_PROMPTS_FROM_ENV = True
        settings.EXPENSE_AGENT_PROMPT = None
        loaded_prompt = get_prompt("expense")
        assert loaded_prompt == DEFAULT_EXPENSE_AGENT_PROMPT
    finally:
        settings.EXPENSE_AGENT_PROMPT = original_setting
