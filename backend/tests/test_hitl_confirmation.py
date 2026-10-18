from unittest.mock import patch
from app.agents.confirmation import (
    create_confirmation_proposal,
    execute_confirmed_action,
    _pending_proposals,
)


def test_confirmation_proposal_creation_and_rejection():
    """Verify proposal registration and rejection workflow without side effects."""
    user_id = 7
    target_tx_id = 101

    with patch("app.agents.confirmation.SessionLocal") as mock_session_factory:
        mock_session = mock_session_factory.return_value
        mock_rec = mock_session.query.return_value.filter.return_value.first.return_value
        mock_rec.type = "expense"
        mock_rec.amount = 5000.0
        mock_rec.category = "Shopping"
        mock_rec.date = "2026-10-10"

        # 1. Create proposal
        proposal = create_confirmation_proposal(
            user_id=user_id,
            action_type="delete_transaction",
            target_id=target_tx_id,
            summary="Delete transaction #101",
            details={"target_id": target_tx_id},
        )

        assert "action_token" in proposal
        action_token = proposal["action_token"]
        assert proposal["status"] == "awaiting_confirmation"

        # 2. Reject proposal
        reject_res = execute_confirmed_action(
            user_id=user_id,
            action_token=action_token,
            confirmed=False,
        )
        assert reject_res["success"] is True
        assert reject_res["status"] == "cancelled"
        assert "No database changes were made" in reject_res["message"]


def test_confirmation_cross_user_isolation():
    """Verify User B cannot confirm or cancel an action proposal belonging to User A."""
    user_a = 10
    user_b = 20

    with patch("app.agents.confirmation.SessionLocal"):
        proposal = create_confirmation_proposal(
            user_id=user_a,
            action_type="delete_transaction",
            target_id=55,
            summary="Delete transaction #55",
            details={"target_id": 55},
        )
        action_token = proposal["action_token"]

        # Attempt execution by User B
        res = execute_confirmed_action(
            user_id=user_b,
            action_token=action_token,
            confirmed=True,
        )
        assert res["success"] is False
        assert "Access denied" in res["error"]


def test_confirmation_idempotency_prevents_duplicate_execution():
    """Verify an already executed proposal cannot be executed again."""
    user_id = 15

    with patch("app.agents.confirmation.SessionLocal"), \
         patch("app.agents.confirmation.delete_transaction_db", return_value={"success": True}):

        proposal = create_confirmation_proposal(
            user_id=user_id,
            action_type="delete_transaction",
            target_id=88,
            summary="Delete transaction #88",
            details={"target_id": 88},
        )
        action_token = proposal["action_token"]

        # First execution (succeeds)
        res1 = execute_confirmed_action(user_id=user_id, action_token=action_token, confirmed=True)
        assert res1["success"] is True

        # Second execution (must fail idempotency check)
        res2 = execute_confirmed_action(user_id=user_id, action_token=action_token, confirmed=True)
        assert res2["success"] is False
        assert "already been processed" in res2["error"] or "expired" in res2["error"]
