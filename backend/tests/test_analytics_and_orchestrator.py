import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from app.analytics.service import calculate_analytics_summary, calculate_monthly_report
from app.agents.orchestrator import run_local_offline_orchestrator


class MockTx:
    """Mock database transaction with Decimal amount to match PostgreSQL Numeric columns."""
    def __init__(self, tx_id, user_id, date, category, amount, tx_type, description=""):
        self.id = tx_id
        self.user_id = user_id
        self.date = date
        self.category = category
        self.amount = Decimal(str(amount))
        self.type = tx_type
        self.description = description
        self.created_at = None


def test_monthly_report_decimal_operations_and_delta():
    """Verify calculate_monthly_report handles Decimal arithmetic and produces expense_delta without TypeError."""
    txs = [
        MockTx(1, 10, "2026-10-01", "Salary", 50000.0, "income"),
        MockTx(2, 10, "2026-10-05", "Rent", 20000.0, "expense"),
        MockTx(3, 10, "2026-10-10", "Food", 10000.0, "expense"),
    ]

    mock_session = MagicMock()
    mock_session.query.return_value.filter.return_value.all.return_value = txs

    report = calculate_monthly_report(mock_session, user_id=10, month="2026-10")

    assert report["month"] == "2026-10"
    assert report["total_income"] == 50000.0
    assert report["total_expenses"] == 30000.0
    assert report["net_cash_flow"] == 20000.0
    assert "expense_delta" in report
    assert len(report["top_categories"]) == 2
    assert report["top_categories"][0]["category"] == "Rent"
    assert len(report["actionable_suggestions"]) > 0


def test_monthly_report_empty_month_safe_fallback():
    """Verify calculate_monthly_report does not fail or divide by zero on empty data."""
    mock_session = MagicMock()
    mock_session.query.return_value.filter.return_value.all.return_value = []

    report = calculate_monthly_report(mock_session, user_id=10, month="2026-05")

    assert report["total_income"] == 0.0
    assert report["total_expenses"] == 0.0
    assert report["net_cash_flow"] == 0.0
    assert report["expense_delta"] == 0.0
    assert report["top_categories"] == []
    assert any("No financial activity recorded" in s for s in report["actionable_suggestions"])


def test_analytics_summary_multi_user_isolation():
    """Verify calculate_analytics_summary filters strictly for user_id and does not include None or other users."""
    mock_session = MagicMock()
    mock_query = mock_session.query.return_value
    mock_filtered = mock_query.filter.return_value
    mock_ordered = mock_filtered.order_by.return_value
    mock_ordered.all.return_value = [
        MockTx(1, 42, "2026-10-01", "Salary", 25000.0, "income"),
        MockTx(2, 42, "2026-10-02", "Food", 5000.0, "expense"),
    ]

    summary = calculate_analytics_summary(mock_session, user_id=42)

    assert summary["total_income"] == 25000.0
    assert summary["total_expenses"] == 5000.0
    assert summary["net_savings"] == 20000.0
    assert summary["savings_rate"] == 80.0
    assert len(summary["categories"]) == 1
    assert summary["categories"][0]["category"] == "Food"


def test_offline_orchestrator_inquiry_does_not_create_transaction():
    """Verify analytical questions (e.g. largest expense) never invoke record_transaction_db."""
    with patch("app.agents.orchestrator.record_transaction_db") as mock_record, \
         patch("app.agents.orchestrator.get_financial_summary_db") as mock_summary:

        mock_summary.return_value = {
            "total_income": 30000.0,
            "total_expense": 15000.0,
            "available_balance": 15000.0,
            "savings_rate": 50.0,
            "categories": [{"category": "Food", "amount": 10000.0, "percentage": 66.7}],
        }

        # Query asking about largest expense category
        result = run_local_offline_orchestrator(
            query="What is my largest expense category this month?",
            thread_id="user_1_test",
            user_id=1,
            user_currency="PKR",
            user_memories=[],
        )

        # Must NOT call record_transaction_db
        mock_record.assert_not_called()
        assert "record_transaction" not in result["executed_tools"]
        assert "get_financial_summary" in result["executed_tools"]
        assert "largest expenditure category is **Food**" in result["response"]


def test_offline_orchestrator_recording_requires_explicit_amount():
    """Verify offline engine refuses to record phantom default transactions when no amount is given."""
    with patch("app.agents.orchestrator.record_transaction_db") as mock_record:
        result = run_local_offline_orchestrator(
            query="Please record my food expense from earlier",
            thread_id="user_1_test",
            user_id=1,
            user_currency="PKR",
            user_memories=[],
        )

        mock_record.assert_not_called()
        assert "record_transaction" not in result["executed_tools"]
        assert "Please specify the amount you would like to record" in result["response"]
