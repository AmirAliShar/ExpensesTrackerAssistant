import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage

from app.memory.checkpointer import get_graph_checkpointer, get_scoped_thread_id
from app.agents.orchestrator import run_finpilot_agent
from app.agents.confirmation import (
    create_confirmation_proposal,
    execute_confirmed_action,
    get_pending_proposal_for_thread,
    clear_pending_proposal_for_thread,
    _pending_proposals,
    _thread_to_action_token,
)
from app.database import SessionLocal, Transaction, User


def _ensure_user(db, user_id: int, email: str):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        u = User(id=user_id, email=email, hashed_password="pwd", full_name=f"User {user_id}")
        db.add(u)
        db.commit()
    return u


@pytest.fixture(autouse=True)
def clean_proposals_cache():
    """Clear memory caches between tests."""
    _pending_proposals.clear()
    _thread_to_action_token.clear()
    yield
    _pending_proposals.clear()
    _thread_to_action_token.clear()


@pytest.mark.asyncio
async def test_multi_turn_delete_confirmation_workflow():
    """
    Verify the complete multi-turn confirmation workflow:
    1. User: 'Delete transaction #99901' -> Assistant asks for confirmation, remembers transaction target.
    2. User: 'Yes, delete it' -> Assistant deletes #99901 without asking for ID again.
    """
    user_id = 999
    thread_id = "test_confirm_workflow_thread"

    with SessionLocal() as db:
        _ensure_user(db, user_id, "test_multi_turn@finpilot.io")
        db.query(Transaction).filter(Transaction.user_id == user_id).delete()
        tx = Transaction(
            id=99901,
            user_id=user_id,
            date="2026-10-14",
            category="Education",
            amount=Decimal("3000.00"),
            type="expense",
            description="College Tuition Fee",
        )
        db.add(tx)
        db.commit()

    try:
        # Turn 1: User asks to delete transaction #99901
        res1 = await run_finpilot_agent(
            query="Delete transaction #99901",
            thread_id=thread_id,
            user_id=user_id,
            user_currency="PKR",
        )

        assert "I found transaction #99901" in res1["response"]
        assert "Education" in res1["response"]
        assert "Do you want to delete it?" in res1["response"]
        assert res1["pending_confirmation"] is not None
        assert res1["pending_confirmation"]["target_transaction_id"] == 99901

        # Turn 2: User confirms without mentioning the ID: 'Yes, delete it.'
        res2 = await run_finpilot_agent(
            query="Yes, delete it.",
            thread_id=thread_id,
            user_id=user_id,
            user_currency="PKR",
        )

        assert "deleted successfully" in res2["response"]
        assert "99901" in res2["response"]
        assert "delete_transaction" in res2["executed_tools"]
        assert res2["pending_confirmation"] is None

        # Verify transaction is permanently deleted in PostgreSQL
        with SessionLocal() as db:
            deleted_tx = db.query(Transaction).filter(Transaction.id == 99901).first()
            assert deleted_tx is None

    finally:
        with SessionLocal() as db:
            db.query(Transaction).filter(Transaction.user_id == user_id).delete()
            db.commit()


@pytest.mark.asyncio
async def test_cancellation_workflow_preserves_transaction():
    """Verify natural cancellation leaves the transaction intact in the database."""
    user_id = 998
    thread_id = "test_cancel_workflow_thread"

    with SessionLocal() as db:
        _ensure_user(db, user_id, "test_cancel@finpilot.io")
        db.query(Transaction).filter(Transaction.user_id == user_id).delete()
        tx = Transaction(
            id=99801,
            user_id=user_id,
            date="2026-10-14",
            category="Shopping",
            amount=Decimal("4500.00"),
            type="expense",
            description="Running Shoes",
        )
        db.add(tx)
        db.commit()

    try:
        # Turn 1: Request deletion
        res1 = await run_finpilot_agent(
            query="Delete transaction #99801",
            thread_id=thread_id,
            user_id=user_id,
            user_currency="PKR",
        )
        assert res1["pending_confirmation"] is not None

        # Turn 2: Cancel
        res2 = await run_finpilot_agent(
            query="No, don't delete it",
            thread_id=thread_id,
            user_id=user_id,
            user_currency="PKR",
        )
        assert "Action cancelled" in res2["response"]
        assert "remains unchanged" in res2["response"]
        assert res2["pending_confirmation"] is None

        # Verify transaction is still preserved in PostgreSQL
        with SessionLocal() as db:
            tx_check = db.query(Transaction).filter(Transaction.id == 99801).first()
            assert tx_check is not None
            assert float(tx_check.amount) == 4500.0

    finally:
        with SessionLocal() as db:
            db.query(Transaction).filter(Transaction.user_id == user_id).delete()
            db.commit()


@pytest.mark.asyncio
async def test_confirmation_without_pending_operation_rejects():
    """Verify saying 'yes' without a prior pending operation executes no financial mutation."""
    res = await run_finpilot_agent(
        query="Yes, go ahead",
        thread_id="empty_pending_thread",
        user_id=997,
        user_currency="PKR",
    )
    assert "no pending operations awaiting your confirmation" in res["response"].lower()
    assert len(res["executed_tools"]) == 0
    assert res["pending_confirmation"] is None


@pytest.mark.asyncio
async def test_cross_user_isolation_for_deletion():
    """Verify User B cannot delete or confirm a transaction owned by User A."""
    user_a = 991
    user_b = 992

    with SessionLocal() as db:
        _ensure_user(db, user_a, "user_a_991@finpilot.io")
        _ensure_user(db, user_b, "user_b_992@finpilot.io")
        db.query(Transaction).filter(Transaction.id == 99101).delete()
        tx = Transaction(
            id=99101,
            user_id=user_a,
            date="2026-10-14",
            category="Rent",
            amount=Decimal("35000.00"),
            type="expense",
            description="Apartment Rent",
        )
        db.add(tx)
        db.commit()

    try:
        # User B attempts to delete User A's transaction
        res = await run_finpilot_agent(
            query="Delete transaction #99101",
            thread_id="user_b_thread",
            user_id=user_b,
            user_currency="PKR",
        )
        assert "not found or not authorized" in res["response"].lower()
        assert res["pending_confirmation"] is None

        # Verify transaction is untouched in PostgreSQL
        with SessionLocal() as db:
            tx_check = db.query(Transaction).filter(Transaction.id == 99101).first()
            assert tx_check is not None
            assert tx_check.user_id == user_a

    finally:
        with SessionLocal() as db:
            db.query(Transaction).filter(Transaction.id == 99101).delete()
            db.commit()


def test_thread_scoped_proposal_indexing():
    """Verify proposal registration is strictly scoped by user and thread."""
    user_id = 501
    tid = "user_501_session_abc"

    with SessionLocal() as db:
        _ensure_user(db, user_id, "user_501@finpilot.io")
        db.query(Transaction).filter(Transaction.id == 50101).delete()
        tx = Transaction(
            id=50101,
            user_id=user_id,
            date="2026-10-14",
            category="Utilities",
            amount=Decimal("2500.00"),
            type="expense",
            description="Electricity Bill",
        )
        db.add(tx)
        db.commit()

    try:
        proposal = create_confirmation_proposal(
            user_id=user_id,
            action_type="delete_transaction",
            target_id=50101,
            summary="Delete #50101",
            details={"target_id": 50101},
            conversation_id=tid,
        )
        assert "action_token" in proposal
        assert proposal["target_transaction_id"] == 50101
        assert proposal["confirmation_status"] == "awaiting_confirmation"

        # Query by thread
        retrieved = get_pending_proposal_for_thread(user_id, tid)
        assert retrieved is not None
        assert retrieved["action_token"] == proposal["action_token"]

        # Different thread returns None
        assert get_pending_proposal_for_thread(user_id, "other_thread") is None

        # Clear thread proposal
        clear_pending_proposal_for_thread(user_id, tid)
        assert get_pending_proposal_for_thread(user_id, tid) is None

    finally:
        with SessionLocal() as db:
            db.query(Transaction).filter(Transaction.id == 50101).delete()
            db.commit()
