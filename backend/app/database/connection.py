import os
from pathlib import Path
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional, List

from dotenv import load_dotenv
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    Numeric,
    String,
    TIMESTAMP,
    Date,
    TEXT,
    Boolean,
    JSON,
    ForeignKey,
    desc,
    CheckConstraint,
    Index,
    UniqueConstraint,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, relationship, sessionmaker

from app.core.config import settings

# Load backend/.env
ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(ENV_PATH, override=True)

# PostgreSQL configuration
PGHOST = os.getenv("PGHOST", "localhost")
PGPORT = int(os.getenv("PGPORT", "5432"))
PGDATABASE = os.getenv("PGDATABASE", "LangGraph")
PGUSER = os.getenv("PGUSER", "postgres")
PGPASSWORD = os.getenv("PGPASSWORD")

if not PGPASSWORD:
    raise RuntimeError(f"PGPASSWORD is missing from {ENV_PATH}")

def create_postgres_engine() -> Engine:
    database_url = settings.DATABASE_URL
    if "sqlite" in database_url.lower():
        raise RuntimeError(
            "SQLite fallback is strictly prohibited. "
            "FinPilot AI requires a reachable PostgreSQL database."
        )
    if not database_url.lower().startswith(("postgresql://", "postgresql+psycopg2://")):
        raise RuntimeError(
            "FinPilot AI requires a PostgreSQL database URL "
            "(postgresql:// or postgresql+psycopg2://)."
        )
    return create_engine(database_url, pool_pre_ping=True)


def verify_database_connection(database_engine: Engine) -> None:
    try:
        with database_engine.connect():
            pass
    except Exception as exc:
        raise RuntimeError(
            "FinPilot AI requires a reachable PostgreSQL database. "
            "Silent SQLite fallback is disabled.\n"
            "Action Required: verify PGHOST, PGPORT, PGDATABASE, PGUSER, and PGPASSWORD "
            f"in backend/.env, then ensure PostgreSQL is running.\n"
            f"Database connection error: {exc}"
        ) from exc


# Database engine and session
engine = create_postgres_engine()
DATABASE_URL = settings.DATABASE_URL

Base = declarative_base()


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Keep all your existing model classes below this line.

class ExpensiveTracker(Base):
    __tablename__ = "expensivetracker"
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    education = Column(Integer, nullable=False, default=0)
    travel = Column(Integer, nullable=False, default=0)
    food = Column(Integer, nullable=False, default=0)
    fruit = Column(Integer, nullable=False, default=0)
    medicine = Column(Integer, nullable=False, default=0)
    friends = Column(Integer, nullable=False, default=0)
    description = Column(TEXT)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    preferred_currency = Column(String(10), default="PKR")
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    budgets = relationship("Budget", back_populates="user", cascade="all, delete-orphan")
    savings_goals = relationship("SavingsGoal", back_populates="user", cascade="all, delete-orphan")
    memories = relationship("UserMemory", back_populates="user", cascade="all, delete-orphan")
    personal_loans = relationship("PersonalLoan", back_populates="user", cascade="all, delete-orphan")


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    date = Column(Date, nullable=False)
    category = Column(String(100), nullable=False, index=True)
    amount = Column(Numeric(precision=12, scale=2), nullable=False)
    type = Column(String(20), nullable=False, default="expense")  # 'expense' or 'income'
    description = Column(TEXT, nullable=True)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    user = relationship("User", back_populates="transactions")


class Budget(Base):
    __tablename__ = "budgets"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    category = Column(String(100), nullable=False)
    monthly_limit = Column(Numeric(precision=12, scale=2), nullable=False)
    month = Column(String(7), nullable=False)  # 'YYYY-MM'
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    user = relationship("User", back_populates="budgets")


class SavingsGoal(Base):
    __tablename__ = "savings_goals"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    target_amount = Column(Numeric(precision=12, scale=2), nullable=False)
    current_amount = Column(Numeric(precision=12, scale=2), nullable=False, default=Decimal("0.00"))
    target_date = Column(Date, nullable=True)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    user = relationship("User", back_populates="savings_goals")


class UserMemory(Base):
    __tablename__ = "user_memories"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    memory_type = Column(String(50), default="preference")  # 'preference', 'fact', 'habit', 'goal'
    content = Column(TEXT, nullable=False)
    source = Column(String(50), default="conversation")
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="memories")


class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    thread_id = Column(String(255), nullable=False, unique=True, index=True)
    title = Column(String(255), nullable=False, default="New conversation")
    archived = Column(Boolean, nullable=False, default=False)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = relationship("ConversationMessage", back_populates="conversation", cascade="all, delete-orphan")


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(TEXT, nullable=False)
    message_metadata = Column("metadata", JSON, nullable=True)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")


class PersonalLoan(Base):
    __tablename__ = "personal_loans"
    __table_args__ = (
        CheckConstraint("loan_type IN ('lent', 'borrowed')", name="ck_personal_loans_type"),
        CheckConstraint("original_amount > 0", name="ck_personal_loans_original_amount"),
        CheckConstraint(
            "outstanding_amount >= 0 AND outstanding_amount <= original_amount",
            name="ck_personal_loans_outstanding_amount",
        ),
        CheckConstraint(
            "status IN ('active', 'partially_paid', 'settled')",
            name="ck_personal_loans_status",
        ),
        Index("ix_personal_loans_user_person", "user_id", "person_name"),
        Index("ix_personal_loans_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    person_name: Mapped[str] = mapped_column(String(255), nullable=False)
    loan_type: Mapped[str] = mapped_column(String(20), nullable=False)
    original_amount: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=2), nullable=False)
    outstanding_amount: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=2), nullable=False)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, default=_utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        default=_utcnow_naive,
        onupdate=_utcnow_naive,
    )

    user: Mapped["User"] = relationship("User", back_populates="personal_loans")
    repayments: Mapped[List["LoanRepayment"]] = relationship(
        "LoanRepayment",
        back_populates="loan",
        cascade="all, delete-orphan",
        order_by="LoanRepayment.repayment_date.desc()",
    )


class LoanRepayment(Base):
    __tablename__ = "loan_repayments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_loan_repayments_amount"),
        UniqueConstraint("idempotency_key", name="uq_loan_repayments_idempotency_key"),
        Index("ix_loan_repayments_loan_date", "loan_id", "repayment_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    loan_id: Mapped[int] = mapped_column(
        ForeignKey("personal_loans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=12, scale=2), nullable=False)
    repayment_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(TEXT, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False, default=_utcnow_naive)

    loan: Mapped["PersonalLoan"] = relationship("PersonalLoan", back_populates="repayments")


def init_database() -> None:
    verify_database_connection(engine)
    try:
        Base.metadata.create_all(engine)
        print("[OK] Database initialized successfully with all models")
        migrate_legacy_records()
    except SQLAlchemyError as exc:
        raise RuntimeError(f"Database schema initialization failed: {exc}") from exc


def migrate_legacy_records() -> None:
    db = SessionLocal()
    try:
        legacy_count = db.query(ExpensiveTracker).count()
        tx_count = db.query(Transaction).count()
        if legacy_count > 0 and tx_count == 0:
            print(f"[MIGRATION] Migrating {legacy_count} legacy records into Transactions table...")
            legacy_records = db.query(ExpensiveTracker).all()
            for rec in legacy_records:
                category_values = {
                    "Education": rec.education,
                    "Travel": rec.travel,
                    "Food": rec.food,
                    "Fruit": rec.fruit,
                    "Medicine": rec.medicine,
                    "Friends": rec.friends
                }
                for cat, val in category_values.items():
                    if val and val > 0:
                        db.add(Transaction(
                            user_id=None,
                            date=rec.date,
                            category=cat,
                            amount=float(val),
                            type="expense",
                            description=rec.description or f"Legacy {cat} expense",
                            created_at=rec.created_at or datetime.utcnow()
                        ))
            db.commit()
            print("[OK] Legacy records migrated safely into Transactions table")
    except Exception as e:
        db.rollback()
        print(f"Migration note: {e}")
    finally:
        db.close()
