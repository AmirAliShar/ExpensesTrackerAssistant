import os
import urllib.parse
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv

def load_environment() -> None:
    """Load environment variables from nearest .env candidate file."""
    backend_env = Path(__file__).resolve().parent.parent.parent / ".env"
    candidates = [
        backend_env,
        Path.cwd() / ".env",
        Path(__file__).resolve().parent.parent.parent.parent / ".env",
    ]
    for p in candidates:
        if p.is_file():
            load_dotenv(dotenv_path=p, override=False)
    load_dotenv()

load_environment()


class Settings:
    """Centralized configuration settings for AI Expense Tracker."""

    # General App Settings
    APP_NAME: str = os.environ.get("APP_NAME", "AI Expense Tracker")
    APP_ENV: str = os.environ.get("APP_ENV", os.environ.get("ENVIRONMENT", "development"))
    DEBUG: bool = os.environ.get("DEBUG", "false").lower() in ("true", "1", "yes")
    HOST: str = os.environ.get("HOST", "0.0.0.0")
    PORT: int = int(os.environ.get("PORT", "8000"))

    # Security & JWT Authentication
    JWT_SECRET_KEY: str = os.environ.get(
        "JWT_SECRET_KEY", "antigravity_super_secret_jwt_key_2026_finance_assistant"
    )
    JWT_ALGORITHM: str = os.environ.get("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

    # CORS
    CORS_ORIGINS: List[str] = [
        origin.strip()
        for origin in os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
        if origin.strip()
    ]

    # Database Configuration (Mandatory PostgreSQL)
    PGHOST: str = os.environ.get("PGHOST", "localhost")
    PGPORT: str = os.environ.get("PGPORT", "5432")
    PGDATABASE: str = os.environ.get("PGDATABASE", "LangGraph")
    PGUSER: Optional[str] = os.environ.get("PGUSER", "postgres")
    PGPASSWORD: Optional[str] = os.environ.get("PGPASSWORD")
    _RAW_DATABASE_URL: Optional[str] = os.environ.get("DATABASE_URL")

    @property
    def DATABASE_URL(self) -> str:
        """
        Build and validate canonical PostgreSQL connection URL.
        Enforces psycopg2 driver and handles credential character escaping safely.
        """
        url = self._RAW_DATABASE_URL
        if url and url.strip():
            url = url.strip()
            # Normalize driver
            if url.startswith("postgresql://"):
                url = "postgresql+psycopg2://" + url[len("postgresql://"):]
            elif not url.startswith("postgresql+psycopg2://"):
                url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
            return url

        user = self.PGUSER or "postgres"
        password = self.PGPASSWORD or ""
        host = self.PGHOST or "localhost"
        port = self.PGPORT or "5432"
        db = self.PGDATABASE or "LangGraph"

        encoded_user = urllib.parse.quote_plus(user)
        if password:
            encoded_password = urllib.parse.quote_plus(password)
            return f"postgresql+psycopg2://{encoded_user}:{encoded_password}@{host}:{port}/{db}"
        return f"postgresql+psycopg2://{encoded_user}@{host}:{port}/{db}"

    # Groq Model & Dynamic Fallback
    GROQ_API_KEY: Optional[str] = os.environ.get("GROQ_API_KEY")
    PRIMARY_CHAT_PROVIDER: str = os.environ.get("PRIMARY_CHAT_PROVIDER", "groq")
    PRIMARY_CHAT_MODEL: str = os.environ.get("PRIMARY_CHAT_MODEL", "llama-3.1-8b-instant")
    _GROQ_FALLBACK_MODELS_STR: str = os.environ.get(
        "GROQ_FALLBACK_MODELS", "llama-3.3-70b-versatile,openai/gpt-oss-120b"
    )
    MODEL_MAX_RETRIES: int = int(os.environ.get("MODEL_MAX_RETRIES", "2"))
    MODEL_TIMEOUT_SECONDS: int = int(os.environ.get("MODEL_TIMEOUT_SECONDS", "60"))

    @property
    def GROQ_FALLBACK_MODELS(self) -> List[str]:
        return [m.strip() for m in self._GROQ_FALLBACK_MODELS_STR.split(",") if m.strip()]

    @property
    def ALL_GROQ_MODELS(self) -> List[str]:
        models = [self.PRIMARY_CHAT_MODEL]
        for m in self.GROQ_FALLBACK_MODELS:
            if m not in models:
                models.append(m)
        for standard_m in ["llama-3.1-8b-instant", "llama-3.3-70b-versatile", "openai/gpt-oss-120b"]:
            if standard_m not in models:
                models.append(standard_m)
        return models

    # Voice (STT & TTS)
    GROQ_STT_MODEL: str = os.environ.get("GROQ_STT_MODEL", "whisper-large-v3-turbo")
    TTS_PROVIDER: str = os.environ.get("TTS_PROVIDER", "edge-tts")
    TTS_MODEL: str = os.environ.get("TTS_MODEL", "en-US-ChristopherNeural")

    # FastMCP
    MCP_SERVER_PORT: int = int(os.environ.get("MCP_SERVER_PORT", "8001"))
    MCP_SERVER_URL: str = os.environ.get("MCP_SERVER_URL", "http://localhost:8001/mcp")

    # Agent Orchestration & Prompts
    AGENT_PROMPTS_FROM_ENV: bool = os.environ.get("AGENT_PROMPTS_FROM_ENV", "true").lower() in ("true", "1", "yes")
    AGENT_MAX_ITERATIONS: int = int(os.environ.get("AGENT_MAX_ITERATIONS", "8"))
    AGENT_TIMEOUT_SECONDS: int = int(os.environ.get("AGENT_TIMEOUT_SECONDS", "60"))

    FINANCE_SUPERVISOR_PROMPT: Optional[str] = os.environ.get("FINANCE_SUPERVISOR_PROMPT")
    EXPENSE_AGENT_PROMPT: Optional[str] = os.environ.get("EXPENSE_AGENT_PROMPT")
    BUDGET_AGENT_PROMPT: Optional[str] = os.environ.get("BUDGET_AGENT_PROMPT")
    ANALYTICS_AGENT_PROMPT: Optional[str] = os.environ.get("ANALYTICS_AGENT_PROMPT")
    MEMORY_AGENT_PROMPT: Optional[str] = os.environ.get("MEMORY_AGENT_PROMPT")
    VOICE_AGENT_PROMPT: Optional[str] = os.environ.get("VOICE_AGENT_PROMPT")

    def get_safe_summary(self) -> dict:
        """Return safe startup configuration summary without sensitive secrets."""
        url_host = self.PGHOST
        url_db = self.PGDATABASE
        if self._RAW_DATABASE_URL:
            try:
                parsed = urllib.parse.urlparse(self._RAW_DATABASE_URL)
                url_host = parsed.hostname or url_host
                url_db = parsed.path.lstrip("/") or url_db
            except Exception:
                pass

        return {
            "app_name": self.APP_NAME,
            "environment": self.APP_ENV,
            "database_target": f"PostgreSQL ({url_host}:{self.PGPORT}/{url_db})",
            "primary_model": self.PRIMARY_CHAT_MODEL,
            "fallback_models": self.GROQ_FALLBACK_MODELS,
            "groq_api_key_configured": bool(self.GROQ_API_KEY and not self.GROQ_API_KEY.startswith("your_")),
            "stt_model": self.GROQ_STT_MODEL,
            "tts_provider": self.TTS_PROVIDER,
            "prompts_from_env": self.AGENT_PROMPTS_FROM_ENV,
        }


settings = Settings()
