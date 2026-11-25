from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.router import router
from app.auth import get_current_user
from app.database import Base, SavingsGoal, User, get_db


def test_goal_delete_allows_active_and_completed_goals_and_scopes_owner():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        owner = User(email="goal-owner@example.test", hashed_password="x", preferred_currency="PKR")
        other = User(email="goal-other@example.test", hashed_password="x", preferred_currency="PKR")
        db.add_all([owner, other])
        db.commit()
        active = SavingsGoal(user_id=owner.id, title="Active", target_amount=Decimal("100"), current_amount=Decimal("20"))
        completed = SavingsGoal(user_id=owner.id, title="Completed", target_amount=Decimal("100"), current_amount=Decimal("100"))
        unrelated = SavingsGoal(user_id=other.id, title="Other user's goal", target_amount=Decimal("50"), current_amount=Decimal("50"))
        db.add_all([active, completed, unrelated])
        db.commit()
        active_id, completed_id, unrelated_id, owner_id = active.id, completed.id, unrelated.id, owner.id

    app = FastAPI()
    app.include_router(router, prefix="/api")

    def override_db():
        with factory() as db:
            yield db

    def override_current_user():
        with factory() as db:
            return db.query(User).filter(User.id == owner_id).one()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_current_user
    try:
        with TestClient(app) as client:
            assert client.delete(f"/api/goals/{active_id}").status_code == 200
            assert client.delete(f"/api/goals/{completed_id}").status_code == 200
            assert client.delete(f"/api/goals/{unrelated_id}").status_code == 404
        with factory() as db:
            assert db.query(SavingsGoal).filter(SavingsGoal.id == unrelated_id).one().title == "Other user's goal"
            assert db.query(SavingsGoal).filter(SavingsGoal.user_id == owner_id).count() == 0
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
