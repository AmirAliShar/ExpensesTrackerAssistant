"""
Prompt loader module supporting dynamic environment overrides with safe version-controlled fallbacks.
"""
from typing import Dict
from app.core.config import settings
from app.agents.prompts.defaults import (
    DEFAULT_FINANCE_SUPERVISOR_PROMPT,
    DEFAULT_EXPENSE_AGENT_PROMPT,
    DEFAULT_BUDGET_AGENT_PROMPT,
    DEFAULT_ANALYTICS_AGENT_PROMPT,
    DEFAULT_MEMORY_AGENT_PROMPT,
    DEFAULT_VOICE_AGENT_PROMPT,
)


def get_prompt(prompt_name: str) -> str:
    """
    Retrieve prompt text by name, checking environment variable overrides if enabled.
    """
    allow_env = settings.AGENT_PROMPTS_FROM_ENV

    if prompt_name == "supervisor":
        if allow_env and settings.FINANCE_SUPERVISOR_PROMPT:
            return settings.FINANCE_SUPERVISOR_PROMPT.strip()
        return DEFAULT_FINANCE_SUPERVISOR_PROMPT

    elif prompt_name == "expense":
        if allow_env and settings.EXPENSE_AGENT_PROMPT:
            return settings.EXPENSE_AGENT_PROMPT.strip()
        return DEFAULT_EXPENSE_AGENT_PROMPT

    elif prompt_name == "budget":
        if allow_env and settings.BUDGET_AGENT_PROMPT:
            return settings.BUDGET_AGENT_PROMPT.strip()
        return DEFAULT_BUDGET_AGENT_PROMPT

    elif prompt_name == "analytics":
        if allow_env and settings.ANALYTICS_AGENT_PROMPT:
            return settings.ANALYTICS_AGENT_PROMPT.strip()
        return DEFAULT_ANALYTICS_AGENT_PROMPT

    elif prompt_name == "memory":
        if allow_env and settings.MEMORY_AGENT_PROMPT:
            return settings.MEMORY_AGENT_PROMPT.strip()
        return DEFAULT_MEMORY_AGENT_PROMPT

    elif prompt_name == "voice":
        if allow_env and settings.VOICE_AGENT_PROMPT:
            return settings.VOICE_AGENT_PROMPT.strip()
        return DEFAULT_VOICE_AGENT_PROMPT

    raise ValueError(f"Unknown prompt name: {prompt_name}")


def get_all_prompts() -> Dict[str, str]:
    """Retrieve mapping of all resolved agent prompts."""
    return {
        "supervisor": get_prompt("supervisor"),
        "expense": get_prompt("expense"),
        "budget": get_prompt("budget"),
        "analytics": get_prompt("analytics"),
        "memory": get_prompt("memory"),
        "voice": get_prompt("voice"),
    }
