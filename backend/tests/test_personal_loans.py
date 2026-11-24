from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.schemas import PersonalLoanOut
from app.agents.confirmation import create_confirmation_proposal, execute_confirmed_action
from app.agents.orchestrator import run_local_offline_orchestrator
from app.auth import get_current_user
from app.api.router import router
from app.database import Base, PersonalLoan, User, get_db
from app.loans.intent import classify_personal_loan_intent
from app.loans.service import (
    LoanConflictError,
    LoanNotFoundError,
    LoanValidationError,
    create_personal_loan,
    find_active_loans_for_person,
    get_loan_history,
    get_loan_summary,
    get_person_outstanding_balance,
    record_loan_repayment,
)


@pytest.fixture
def loan_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    users = [
        User(
            email="loan-user-a@example.test",
            hashed_password="x",
            preferred_currency="PKR",
            created_at=datetime(2026, 1, 1),
        ),
        User(
            email="loan-user-b@example.test",
            hashed_password="x",
            preferred_currency="PKR",
            created_at=datetime(2026, 1, 1),
        ),
    ]
    session.add_all(users)
    session.commit()
    user_ids = [user.id for user in users]
    try:
        yield session, user_ids
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def create_lent_loan(db, user_id, person="Arslan", amount="1200.00"):
    return create_personal_loan(
        db,
        user_id=user_id,
        person_name=person,
        loan_type="lent",
        amount=amount,
        transaction_date=None,
    )


def test_partial_and_full_repayments_set_balance_and_status(loan_db):
    db, (user_id, _) = loan_db
    loan = create_lent_loan(db, user_id)

    partial, updated, created = record_loan_repayment(
        db,
        user_id=user_id,
        loan_id=loan.id,
        amount="500.00",
        idempotency_key="repayment-partial-1",
        expected_loan_type="lent",
    )
    assert created is True
    assert partial.amount == Decimal("500.00")
    assert updated.outstanding_amount == Decimal("700.00")
    assert updated.status == "partially_paid"

    _, settled, _ = record_loan_repayment(
        db,
        user_id=user_id,
        loan_id=loan.id,
        amount="700.00",
        idempotency_key="repayment-final-1",
        expected_loan_type="lent",
    )
    assert settled.outstanding_amount == Decimal("0.00")
    assert settled.status == "settled"


def test_borrowing_repayment_reduces_liability(loan_db):
    db, (user_id, _) = loan_db
    loan = create_personal_loan(
        db,
        user_id=user_id,
        person_name="brother",
        loan_type="borrowed",
        amount="5000.00",
    )
    _, updated, created = record_loan_repayment(
        db,
        user_id=user_id,
        loan_id=loan.id,
        amount="2000.00",
        idempotency_key="borrower-repayment-1",
        expected_loan_type="borrowed",
    )
    assert created is True
    assert updated.outstanding_amount == Decimal("3000.00")
    assert updated.status == "partially_paid"
    assert get_loan_summary(db, user_id)["outstanding_liabilities"] == Decimal("3000.00")


def test_repayment_idempotency_and_overpayment_protection(loan_db):
    db, (user_id, _) = loan_db
    loan = create_lent_loan(db, user_id, amount="100.00")
    first, _, created = record_loan_repayment(
        db,
        user_id=user_id,
        loan_id=loan.id,
        amount="25.00",
        idempotency_key="same-repayment-key",
    )
    replay, same_loan, replay_created = record_loan_repayment(
        db,
        user_id=user_id,
        loan_id=loan.id,
        amount="25.00",
        idempotency_key="same-repayment-key",
    )
    assert created and not replay_created
    assert replay.id == first.id
    assert same_loan.outstanding_amount == Decimal("75.00")

    with pytest.raises(LoanConflictError, match="exceeds"):
        record_loan_repayment(
            db,
            user_id=user_id,
            loan_id=loan.id,
            amount="75.01",
            idempotency_key="overpayment-key",
        )
    assert loan.outstanding_amount == Decimal("75.00")


def test_user_scoping_same_names_and_response_schema(loan_db):
    db, (user_a, user_b) = loan_db
    own_loan = create_lent_loan(db, user_a, person="Sam", amount="400.00")
    create_lent_loan(db, user_a, person="Sam", amount="800.00")
    other_users_loan = create_lent_loan(db, user_b, person="Sam", amount="999.00")

    same_name_loans = find_active_loans_for_person(db, user_a, "Sam", "lent")
    assert len(same_name_loans) == 2
    assert {loan.user_id for loan in same_name_loans} == {user_a}
    assert get_loan_history(db, user_a, other_users_loan.id) is None
    with pytest.raises(LoanNotFoundError):
        record_loan_repayment(
            db,
            user_id=user_a,
            loan_id=other_users_loan.id,
            amount="10.00",
            idempotency_key="cross-user-repayment",
        )

    balance = get_person_outstanding_balance(db, user_a, person_name="Sam", loan_type="lent")
    summary = get_loan_summary(db, user_a)
    assert balance["total_receivable"] == Decimal("1200.00")
    assert summary["outstanding_receivables"] == Decimal("1200.00")
    assert summary["outstanding_liabilities"] == Decimal("0.00")
    assert PersonalLoanOut.model_validate(own_loan).user_id == user_a


def test_invalid_amounts_are_rejected(loan_db):
    db, (user_id, _) = loan_db
    with pytest.raises(LoanValidationError):
        create_personal_loan(
            db,
            user_id=user_id,
            person_name="Arslan",
            loan_type="lent",
            amount="1.005",
        )
    loan = create_lent_loan(db, user_id, amount="10.00")
    with pytest.raises(LoanValidationError):
        record_loan_repayment(
            db,
            user_id=user_id,
            loan_id=loan.id,
            amount="0",
            idempotency_key="invalid-amount",
        )


@pytest.mark.parametrize(
    ("query", "expected_action", "expected_type", "expected_person", "expected_amount"),
    [
        ("I gave Arslan Rs. 1,200 to borrow", "create_lending", "lent", "Arslan", "1200"),
        ("I borrowed Rs. 5,000 from my brother", "create_borrowing", "borrowed", "brother", "5000"),
        ("Arslan returned Rs. 500", "repayment_lending", "lent", "Arslan", "500"),
        ("I returned Rs. 2,000 to my brother", "repayment_borrowing", "borrowed", "brother", "2000"),
    ],
)
def test_explicit_loan_language_is_classified(query, expected_action, expected_type, expected_person, expected_amount):
    intent = classify_personal_loan_intent(query)
    assert intent is not None
    assert intent.action == expected_action
    assert intent.loan_type == expected_type
    assert intent.person_name == expected_person
    assert str(intent.amount) == expected_amount


def test_ambiguous_transfers_and_contextual_clarification():
    intent = classify_personal_loan_intent("I gave Arslan Rs. 1,200")
    assert intent is not None and intent.action == "ambiguous_transfer"
    assert intent.amount == Decimal("1200")
    gift_intent = classify_personal_loan_intent("I gave Arslan Rs. 1,200 as a gift")
    assert gift_intent is not None and gift_intent.action == "gift_expense"
    assert classify_personal_loan_intent("I paid the mechanic Rs. 1,200 for a repair") is None

    from langchain_core.messages import AIMessage, HumanMessage

    context = [
        HumanMessage(content="I gave Arslan Rs. 1,200"),
        AIMessage(content="Was this a loan, a gift, or a payment for something?"),
    ]
    follow_up = classify_personal_loan_intent("It was a loan", context)
    assert follow_up is not None
    assert follow_up.action == "create_lending"
    assert follow_up.person_name == "Arslan"
    assert follow_up.amount == Decimal("1200")
    gift_follow_up = classify_personal_loan_intent("It was a gift", context)
    assert gift_follow_up is not None
    assert gift_follow_up.action == "gift_expense"
    assert gift_follow_up.amount == Decimal("1200")

    missing_amount_context = [
        HumanMessage(content="I lent Arslan"),
        AIMessage(content="What amount should I record for Arslan?"),
    ]
    amount_follow_up = classify_personal_loan_intent("1200", missing_amount_context)
    assert amount_follow_up is not None
    assert amount_follow_up.action == "create_lending"
    assert amount_follow_up.person_name == "Arslan"
    assert amount_follow_up.amount == Decimal("1200")


def test_outstanding_questions_are_classified_deterministically():
    lent_balance = classify_personal_loan_intent("How much does Arslan still owe me?")
    liability = classify_personal_loan_intent("How much money do I owe my friends?")
    outstanding = classify_personal_loan_intent("Show all my pending loans")

    assert lent_balance is not None and lent_balance.action == "balance"
    assert lent_balance.loan_type == "lent" and lent_balance.person_name == "Arslan"
    assert liability is not None and liability.action == "balance"
    assert liability.loan_type == "borrowed" and liability.person_name is None
    assert outstanding is not None and outstanding.action == "outstanding"


def test_offline_agent_loan_write_requires_confirmation():
    fake_proposal = {
        "action_token": "act_test_loan",
        "action_type": "create_lending_record",
        "status": "awaiting_confirmation",
        "summary": "Record lent loan",
    }
    with patch("app.agents.orchestrator.create_confirmation_proposal", return_value=fake_proposal), \
         patch("app.agents.orchestrator.record_transaction_db") as record_expense:
        result = run_local_offline_orchestrator(
            query="I gave Arslan Rs. 1,200 to borrow",
            thread_id="loan-thread",
            user_id=42,
            user_currency="PKR",
            user_memories=[],
        )

    record_expense.assert_not_called()
    assert result["pending_confirmation"] == fake_proposal
    assert result["executed_tools"] == ["request_confirmation"]
    assert "PKR 1,200.00" in result["response"]

    from app.agents.orchestrator import FINPILOT_TOOLS

    tool_names = {tool.__name__ for tool in FINPILOT_TOOLS}
    assert {
        "create_lending_record",
        "create_borrowing_record",
        "record_lending_repayment",
        "record_borrowing_repayment",
        "get_person_loan_history",
        "get_person_outstanding_balance",
        "get_all_outstanding_loans",
        "get_loan_summary",
    }.issubset(tool_names)


def test_confirmation_creates_a_user_scoped_loan_only_after_approval(loan_db, monkeypatch):
    db, (user_id, _) = loan_db
    factory = sessionmaker(bind=db.get_bind())
    monkeypatch.setattr("app.agents.confirmation.SessionLocal", factory)

    proposal = create_confirmation_proposal(
        user_id=user_id,
        action_type="create_borrowing_record",
        target_id=0,
        summary="Borrow PKR 500 from my brother",
        details={
            "person_name": "brother",
            "amount": "500.00",
            "transaction_date": None,
            "due_date": None,
            "description": None,
        },
    )
    assert db.query(PersonalLoan).count() == 0

    result = execute_confirmed_action(user_id, proposal["action_token"], confirmed=True)
    assert result["success"] is True
    loan = db.query(PersonalLoan).one()
    assert loan.user_id == user_id
    assert loan.loan_type == "borrowed"
    assert loan.original_amount == Decimal("500.00")


def test_confirmed_lending_repayment_uses_idempotent_service(loan_db, monkeypatch):
    db, (user_id, _) = loan_db
    loan = create_lent_loan(db, user_id, amount="250.00")
    factory = sessionmaker(bind=db.get_bind())
    monkeypatch.setattr("app.agents.confirmation.SessionLocal", factory)

    proposal = create_confirmation_proposal(
        user_id=user_id,
        action_type="record_lending_repayment",
        target_id=loan.id,
        summary="Record repayment from Arslan",
        details={"amount": "75.00", "repayment_date": None, "description": None},
    )
    result = execute_confirmed_action(user_id, proposal["action_token"], confirmed=True)

    assert result["success"] is True
    db.refresh(loan)
    assert loan.outstanding_amount == Decimal("175.00")
    assert loan.status == "partially_paid"


def test_loan_api_requires_confirmation_and_scopes_records_to_user(loan_db):
    db, (user_a, user_b) = loan_db
    app = FastAPI()
    app.include_router(router, prefix="/api")
    session_factory = sessionmaker(bind=db.get_bind())

    def override_db():
        with session_factory() as session:
            yield session

    def override_current_user():
        with session_factory() as session:
            return session.query(User).filter(User.id == user_a).one()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_current_user

    try:
        with TestClient(app) as client:
            loan_payload = {
                "person_name": "Arslan",
                "loan_type": "lent",
                "original_amount": "100.00",
                "transaction_date": "2026-11-24",
                "confirmed": False,
            }
            assert client.post("/api/loans", json=loan_payload).status_code == 400
            loan_payload["confirmed"] = True
            created = client.post("/api/loans", json=loan_payload)
            assert created.status_code == 201
            loan_id = created.json()["id"]
            assert created.json()["original_amount"] == "100.00"

            create_lent_loan(db, user_b, person="Arslan", amount="999.00")
            assert client.get("/api/loans").status_code == 200
            assert len(client.get("/api/loans").json()) == 1
            assert client.get(f"/api/loans/{db.query(PersonalLoan).filter(PersonalLoan.user_id == user_b).one().id}/history").status_code == 404

            repayment_payload = {
                "amount": "50.00",
                "repayment_date": "2026-11-24",
                "idempotency_key": "api-repayment-001",
                "confirmed": False,
            }
            assert client.post(f"/api/loans/{loan_id}/repayments", json=repayment_payload).status_code == 400
            repayment_payload["confirmed"] = True
            repayment = client.post(f"/api/loans/{loan_id}/repayments", json=repayment_payload)
            assert repayment.status_code == 201
            assert repayment.json()["loan"]["outstanding_amount"] == "50.00"
            replay = client.post(f"/api/loans/{loan_id}/repayments", json=repayment_payload)
            assert replay.status_code == 201
            assert replay.json()["created"] is False
            assert len(client.get(f"/api/loans/{loan_id}/history").json()["repayments"]) == 1
    finally:
        app.dependency_overrides.clear()
