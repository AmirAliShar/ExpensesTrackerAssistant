from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import LoanRepayment, PersonalLoan

CENT = Decimal("0.01")
MAX_AMOUNT = Decimal("9999999999.99")


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class LoanValidationError(ValueError):
    pass


class LoanNotFoundError(LookupError):
    pass


class LoanConflictError(ValueError):
    pass


def _validated_amount(value: Any) -> Decimal:
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount <= 0 or amount > MAX_AMOUNT:
            raise LoanValidationError("Amount must be positive and within the supported monetary range.")
        quantized = amount.quantize(CENT)
    except (InvalidOperation, ValueError, TypeError) as exc:
        if isinstance(exc, LoanValidationError):
            raise
        raise LoanValidationError("Enter a valid monetary amount with at most two decimal places.") from exc
    if amount != quantized:
        raise LoanValidationError("Amounts may have no more than two decimal places.")
    return quantized


def _default_date(value: Optional[date]) -> date:
    return value or _utcnow_naive().date()


def create_personal_loan(
    db: Session,
    *,
    user_id: int,
    person_name: str,
    loan_type: str,
    amount: Any,
    transaction_date: Optional[date] = None,
    due_date: Optional[date] = None,
    description: Optional[str] = None,
) -> PersonalLoan:
    clean_name = person_name.strip()
    clean_type = loan_type.strip().lower()
    if not clean_name:
        raise LoanValidationError("Person name cannot be empty.")
    if len(clean_name) > 255:
        raise LoanValidationError("Person name must be 255 characters or fewer.")
    if clean_type not in {"lent", "borrowed"}:
        raise LoanValidationError("Loan type must be 'lent' or 'borrowed'.")

    dec_amount = _validated_amount(amount)
    loan = PersonalLoan(
        user_id=user_id,
        person_name=clean_name,
        loan_type=clean_type,
        original_amount=dec_amount,
        outstanding_amount=dec_amount,
        transaction_date=_default_date(transaction_date),
        due_date=due_date,
        description=(description or "").strip() or None,
        status="active",
        created_at=_utcnow_naive(),
        updated_at=_utcnow_naive(),
    )
    try:
        db.add(loan)
        db.commit()
        db.refresh(loan)
        return loan
    except Exception:
        db.rollback()
        raise


def record_loan_repayment(
    db: Session,
    *,
    user_id: int,
    loan_id: int,
    amount: Any,
    idempotency_key: str,
    expected_loan_type: Optional[str] = None,
    repayment_date: Optional[date] = None,
    description: Optional[str] = None,
) -> tuple[LoanRepayment, PersonalLoan, bool]:
    dec_amount = _validated_amount(amount)
    key = idempotency_key.strip()
    if not key or len(key) > 64:
        raise LoanValidationError("A valid repayment idempotency key is required.")

    try:
        existing = (
            db.query(LoanRepayment)
            .join(PersonalLoan, PersonalLoan.id == LoanRepayment.loan_id)
            .filter(
                LoanRepayment.idempotency_key == key,
                PersonalLoan.user_id == user_id,
            )
            .first()
        )
        if existing:
            if (
                existing.loan_id != loan_id
                or existing.amount != dec_amount
                or (expected_loan_type and existing.loan.loan_type != expected_loan_type)
            ):
                raise LoanConflictError("This repayment request key was already used for a different repayment.")
            return existing, existing.loan, False

        loan = (
            db.query(PersonalLoan)
            .filter(PersonalLoan.id == loan_id, PersonalLoan.user_id == user_id)
            .with_for_update()
            .first()
        )
        if not loan:
            raise LoanNotFoundError("Loan not found or access denied.")
        if expected_loan_type and loan.loan_type != expected_loan_type:
            raise LoanConflictError("The selected loan does not match the repayment direction.")
        if loan.status == "settled" or loan.outstanding_amount <= 0:
            raise LoanConflictError("This loan is already settled.")
        if dec_amount > loan.outstanding_amount:
            raise LoanConflictError(
                f"Repayment exceeds the outstanding balance of {loan.outstanding_amount:.2f}."
            )

        repayment = LoanRepayment(
            loan_id=loan.id,
            amount=dec_amount,
            repayment_date=_default_date(repayment_date),
            description=(description or "").strip() or None,
            idempotency_key=key,
            created_at=_utcnow_naive(),
        )
        loan.outstanding_amount = (loan.outstanding_amount - dec_amount).quantize(CENT)
        loan.status = "settled" if loan.outstanding_amount == 0 else "partially_paid"
        loan.updated_at = _utcnow_naive()
        db.add(repayment)
        db.commit()
        db.refresh(repayment)
        db.refresh(loan)
        return repayment, loan, True
    except IntegrityError as exc:
        db.rollback()
        duplicate = (
            db.query(LoanRepayment)
            .join(PersonalLoan, PersonalLoan.id == LoanRepayment.loan_id)
            .filter(
                LoanRepayment.idempotency_key == key,
                PersonalLoan.user_id == user_id,
            )
            .first()
        )
        if duplicate and duplicate.loan_id == loan_id and duplicate.amount == dec_amount:
            return duplicate, duplicate.loan, False
        raise LoanConflictError("This repayment request has already been processed.") from exc
    except Exception:
        db.rollback()
        raise


def list_personal_loans(
    db: Session,
    user_id: int,
    *,
    loan_type: Optional[str] = None,
    status: Optional[str] = None,
    person_name: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[PersonalLoan]:
    query = db.query(PersonalLoan).filter(PersonalLoan.user_id == user_id)
    if loan_type:
        query = query.filter(PersonalLoan.loan_type == loan_type)
    if status:
        query = query.filter(PersonalLoan.status == status)
    if person_name:
        query = query.filter(PersonalLoan.person_name.ilike(f"%{person_name.strip()}%"))
    return query.order_by(PersonalLoan.transaction_date.desc(), PersonalLoan.id.desc()).offset(offset).limit(limit).all()


def get_all_outstanding_loans(db: Session, user_id: int, loan_type: Optional[str] = None) -> list[PersonalLoan]:
    query = db.query(PersonalLoan).filter(
        PersonalLoan.user_id == user_id,
        PersonalLoan.status.in_(("active", "partially_paid")),
    )
    if loan_type:
        query = query.filter(PersonalLoan.loan_type == loan_type)
    return query.order_by(PersonalLoan.transaction_date.desc(), PersonalLoan.id.desc()).limit(500).all()


def find_active_loans_for_person(
    db: Session,
    user_id: int,
    person_name: str,
    loan_type: str,
) -> list[PersonalLoan]:
    return (
        db.query(PersonalLoan)
        .filter(
            PersonalLoan.user_id == user_id,
            PersonalLoan.person_name.ilike(person_name.strip()),
            PersonalLoan.loan_type == loan_type,
            PersonalLoan.status.in_(("active", "partially_paid")),
        )
        .order_by(PersonalLoan.transaction_date.desc(), PersonalLoan.id.desc())
        .all()
    )


def get_person_loan_history(
    db: Session,
    user_id: int,
    person_name: str,
    loan_type: Optional[str] = None,
) -> list[PersonalLoan]:
    query = db.query(PersonalLoan).filter(
        PersonalLoan.user_id == user_id,
        PersonalLoan.person_name.ilike(person_name.strip()),
    )
    if loan_type:
        query = query.filter(PersonalLoan.loan_type == loan_type)
    return query.order_by(PersonalLoan.transaction_date.desc(), PersonalLoan.id.desc()).all()


def get_loan_history(db: Session, user_id: int, loan_id: int) -> Optional[dict[str, Any]]:
    loan = db.query(PersonalLoan).filter(
        PersonalLoan.id == loan_id,
        PersonalLoan.user_id == user_id,
    ).first()
    if not loan:
        return None
    repayments = (
        db.query(LoanRepayment)
        .filter(LoanRepayment.loan_id == loan.id)
        .order_by(LoanRepayment.repayment_date.desc(), LoanRepayment.id.desc())
        .all()
    )
    return {"loan": loan, "repayments": repayments}


def get_person_outstanding_balance(
    db: Session,
    user_id: int,
    person_name: Optional[str] = None,
    loan_type: Optional[str] = None,
) -> dict[str, Any]:
    query = db.query(PersonalLoan).filter(
        PersonalLoan.user_id == user_id,
        PersonalLoan.status != "settled",
    )
    if person_name:
        query = query.filter(PersonalLoan.person_name.ilike(person_name.strip()))
    loans = query.all()
    receivable = sum(
        (loan.outstanding_amount for loan in loans if loan.loan_type == "lent"),
        Decimal("0.00"),
    )
    liability = sum(
        (loan.outstanding_amount for loan in loans if loan.loan_type == "borrowed"),
        Decimal("0.00"),
    )
    if loan_type == "lent":
        liability = Decimal("0.00")
    elif loan_type == "borrowed":
        receivable = Decimal("0.00")
    return {
        "person_name": person_name,
        "total_receivable": receivable,
        "total_liability": liability,
        "loans": loans,
    }


def get_loan_summary(db: Session, user_id: int) -> dict[str, Any]:
    loans = db.query(PersonalLoan).filter(PersonalLoan.user_id == user_id).all()
    return {
        "total_lent": sum((loan.original_amount for loan in loans if loan.loan_type == "lent"), Decimal("0.00")),
        "total_borrowed": sum((loan.original_amount for loan in loans if loan.loan_type == "borrowed"), Decimal("0.00")),
        "outstanding_receivables": sum(
            (loan.outstanding_amount for loan in loans if loan.loan_type == "lent" and loan.status != "settled"),
            Decimal("0.00"),
        ),
        "outstanding_liabilities": sum(
            (loan.outstanding_amount for loan in loans if loan.loan_type == "borrowed" and loan.status != "settled"),
            Decimal("0.00"),
        ),
        "active_count": sum(1 for loan in loans if loan.status != "settled"),
        "settled_count": sum(1 for loan in loans if loan.status == "settled"),
    }
