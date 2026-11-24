from datetime import datetime, timedelta
from decimal import Decimal

from app.analytics.service import calculate_daily_briefing
from app.database import SessionLocal, User, Transaction, Budget, SavingsGoal
from app.memory.conversations import ensure_conversation, append_turn, list_conversations, get_conversation


def _ensure_user(db, user_id: int, email: str):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        user = User(id=user_id, email=email, hashed_password="pwd", full_name=f"User {user_id}")
        db.add(user)
        db.commit()
    return user


def test_daily_briefing_uses_only_user_records():
    user_id = 701
    with SessionLocal() as db:
        _ensure_user(db, user_id, "briefing701@finpilot.io")
        db.query(Transaction).filter(Transaction.user_id == user_id).delete()
        db.query(Budget).filter(Budget.user_id == user_id).delete()
        db.query(SavingsGoal).filter(SavingsGoal.user_id == user_id).delete()
        today = datetime.utcnow().date()
        yesterday = today - timedelta(days=1)
        db.add(Transaction(
            user_id=user_id,
            date=yesterday,
            category="Food",
            amount=Decimal("1200.00"),
            type="expense",
            description="Yesterday lunch",
        ))
        db.add(Budget(
            user_id=user_id,
            category="Overall",
            monthly_limit=Decimal("20000.00"),
            month=today.strftime("%Y-%m"),
        ))
        db.add(SavingsGoal(
            user_id=user_id,
            title="Emergency Fund",
            target_amount=Decimal("100000.00"),
            current_amount=Decimal("25000.00"),
        ))
        db.commit()

        briefing = calculate_daily_briefing(db, user_id)
        assert briefing["yesterday_spending"] == 1200.0
        assert briefing["remaining_monthly_budget"] == 18800.0
        assert briefing["savings_goals"][0]["progress_percentage"] == 25.0

        db.query(Transaction).filter(Transaction.user_id == user_id).delete()
        db.query(Budget).filter(Budget.user_id == user_id).delete()
        db.query(SavingsGoal).filter(SavingsGoal.user_id == user_id).delete()
        db.commit()


def test_conversation_registry_isolated_by_user():
    user_a, user_b = 702, 703
    with SessionLocal() as db:
        _ensure_user(db, user_a, "conversation702@finpilot.io")
        _ensure_user(db, user_b, "conversation703@finpilot.io")
        conversation_a = ensure_conversation(db, user_a, "session_shared_test", "User A chat")
        append_turn(db, user_a, conversation_a.thread_id, "How much did I spend?", "Verified answer.")

        assert get_conversation(db, user_b, conversation_a.thread_id) is None
        assert len(list_conversations(db, user_b, include_archived=True)) == 0

        conversation_a.title = "Renamed"
        db.commit()
        restored = get_conversation(db, user_a, conversation_a.thread_id)
        assert restored is not None
        assert restored.title == "Renamed"

        db.delete(restored)
        db.commit()
