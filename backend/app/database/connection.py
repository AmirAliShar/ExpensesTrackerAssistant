import os
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal

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
    ForeignKey,
    desc,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

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
