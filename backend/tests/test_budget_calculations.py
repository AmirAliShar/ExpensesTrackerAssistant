from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.analytics.service import budget_usage_percentage, calculate_monthly_budget_usage
from app.database import Budget, Transaction


@pytest.mark.parametrize(
    ("spent", "limit_value", "expected"),
    [
        ("2600", "10000", 26.0),
        ("5000", "10000", 50.0),
        ("0", "10000", 0.0),
        ("12000", "10000", 120.0),
        ("100", "0", 0.0),
    ],
)
def test_budget_usage_percentage(spent, limit_value, expected):
    assert budget_usage_percentage(Decimal(spent), Decimal(limit_value)) == expected


def test_monthly_budget_usage_is_expense_only_period_scoped_and_case_insensitive():
    budget = SimpleNamespace(category="Education", monthly_limit=Decimal("10000.00"))
    txs = [
        SimpleNamespace(category=" education ", amount=Decimal("2600.00")),
    ]
    db = MagicMock()
    budget_query = MagicMock()
    budget_query.filter.return_value.all.return_value = [budget]
    expense_query = MagicMock()
    expense_query.filter.return_value.all.return_value = txs
    db.query.side_effect = [budget_query, expense_query]

    usage = calculate_monthly_budget_usage(db, user_id=7, month="2026-11")

    assert usage[0]["spent"] == Decimal("2600.00")
    assert usage[0]["utilization_percentage"] == 26.0
    budget_filters = budget_query.filter.call_args.args
    expense_filters = expense_query.filter.call_args.args
    assert [condition.right.value for condition in budget_filters] == [7, "2026-11"]
    assert [condition.right.value for condition in expense_filters] == [7, "expense", "2026-11%"]

