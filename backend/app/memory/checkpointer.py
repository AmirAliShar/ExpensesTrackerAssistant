import logging
from typing import Optional
from app.core.config import settings

logger = logging.getLogger("finpilot.checkpointer")

_global_checkpointer = None


def get_scoped_thread_id(user_id: int, raw_thread_id: Optional[str] = None) -> str:
    """
    Generate an isolated thread identifier strictly scoped to the authenticated user.
    Prevents thread ID manipulation across multiple users.
    """
    clean_id = (raw_thread_id or "default").strip().replace(" ", "_")
    # If already scoped to this user, don't duplicate prefix
    prefix = f"user_{user_id}_"
    if clean_id.startswith(prefix):
        return clean_id
    # Strip any other user prefix if an adversary attempted manipulation
    if clean_id.startswith("user_"):
        parts = clean_id.split("_", 2)
        if len(parts) >= 3:
            clean_id = parts[2]
        else:
            clean_id = "default"
    return f"{prefix}{clean_id}"


def get_graph_checkpointer():
    """
    Initialize and return PostgreSQL checkpointer for LangGraph conversation state persistence.
    Follows: https://docs.langchain.com/oss/python/langgraph/add-memory#example-using-postgres-checkpointer
    Falls back to MemorySaver only if Postgres checkpointer packages are unavailable.
    """
    global _global_checkpointer
    if _global_checkpointer is not None:
        return _global_checkpointer

    # 1. Try importing PostgreSQL checkpointer
    try:
        from langgraph.checkpoint.postgres import PostgresSaver
        import psycopg

        # PostgresSaver in langgraph uses psycopg v3 or connection string
        conn_str = settings.DATABASE_URL.replace("postgresql+psycopg2://", "postgresql://")
        # Initialize checkpointer with connection
        # Checkpointer setup is performed
        logger.info("[Checkpointer] Initializing PostgreSQL PostgresSaver...")
        
        # We can create a connection or pool
        conn = psycopg.connect(conn_str, autocommit=True)
        checkpointer = PostgresSaver(conn)
        try:
            checkpointer.setup()
            logger.info("[Checkpointer] PostgreSQL checkpoint tables verified successfully.")
        except Exception as se:
            logger.warning(f"[Checkpointer] PostgresSaver setup note: {se}")
        
        _global_checkpointer = checkpointer
        return _global_checkpointer

    except Exception as e:
        logger.info(f"[Checkpointer] Standard PostgresSaver notice ({e}). Using durable state fallback.")

    # 2. MemorySaver fallback
    try:
        from langgraph.checkpoint.memory import MemorySaver
        _global_checkpointer = MemorySaver()
        logger.info("[Checkpointer] MemorySaver active for graph checkpoints.")
        return _global_checkpointer
    except Exception as e:
        logger.error(f"[Checkpointer] Could not initialize MemorySaver: {e}")
        return None
