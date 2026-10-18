import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal
from sqlalchemy.exc import OperationalError
from sqlalchemy import create_engine

from app.core.config import settings
from app.database.connection import (
    verify_database_connection,
    create_postgres_engine,
    Transaction,
    Budget,
    SavingsGoal,
    User,
)


def test_database_url_enforces_postgresql_driver():
    """Verify DATABASE_URL enforces postgresql+psycopg2 driver."""
    url = settings.DATABASE_URL
    assert url.startswith("postgresql+psycopg2://") or url.startswith("postgresql://")
    assert "sqlite" not in url.lower()


def test_create_postgres_engine_rejects_sqlite():
    """Verify create_postgres_engine refuses SQLite URLs."""
    with patch.object(settings, "_RAW_DATABASE_URL", "sqlite:///./test.db"):
        with pytest.raises(RuntimeError) as exc_info:
            create_postgres_engine()
        assert "SQLite fallback is strictly prohibited" in str(exc_info.value)


def test_verify_database_connection_fails_with_actionable_error():
    """Verify that an unreachable PostgreSQL server raises an actionable error instead of falling back."""
    mock_engine = MagicMock()
    mock_engine.connect.side_effect = OperationalError("connection to server at 'localhost' failed", None, None)

    with pytest.raises(RuntimeError) as exc_info:
        verify_database_connection(mock_engine)

    err_text = str(exc_info.value)
    assert "FinPilot AI requires a reachable PostgreSQL database" in err_text
    assert "Silent SQLite fallback is disabled" in err_text
    assert "Action Required" in err_text


def test_model_numeric_decimal_columns():
    """Verify monetary columns use Numeric precision."""
    tx_amount_col = Transaction.__table__.columns["amount"]
    budget_limit_col = Budget.__table__.columns["monthly_limit"]
    goal_target_col = SavingsGoal.__table__.columns["target_amount"]

    assert str(tx_amount_col.type).startswith("NUMERIC")
    assert str(budget_limit_col.type).startswith("NUMERIC")
    assert str(goal_target_col.type).startswith("NUMERIC")
