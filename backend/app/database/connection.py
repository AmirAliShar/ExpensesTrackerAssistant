import sys
import logging
from datetime import datetime
from decimal import Decimal
from typing import Generator

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
    text,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.core.config import settings

logger = logging.getLogger("finpilot.database")

Base = declarative_base()


def verify_database_connection(test_engine=None) -> bool:
    """
    Verify PostgreSQL connectivity without logging sensitive credentials.
    Raises RuntimeError with actionable message if unreachable.
    """
    eng = test_engine or engine
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except OperationalError as e:
        error_msg = (
            f"\n[FATAL] FinPilot AI requires a reachable PostgreSQL database.\n"
            f"Failed to connect to configured host '{settings.PGHOST}:{settings.PGPORT}' "
            f"and database '{settings.PGDATABASE}'.\n"
            f"Error details: {e.orig if hasattr(e, 'orig') else str(e)}\n\n"
            f"Action Required:\n"
            f"1. Ensure PostgreSQL is installed and running on port {settings.PGPORT}.\n"
            f"2. Verify PGDATABASE='{settings.PGDATABASE}', PGUSER, and PGPASSWORD in your .env file.\n"
            f"3. Create the database if it doesn't exist: CREATE DATABASE \"{settings.PGDATABASE}\";\n"
            f"4. Note: Silent SQLite fallback is disabled in production to guarantee data consistency.\n"
        )
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e
    except Exception as e:
        error_msg = f"[FATAL] PostgreSQL initialization failed: {str(e)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e


def create_postgres_engine():
    """Create SQLAlchemy engine strictly bound to PostgreSQL."""
    db_url = settings.DATABASE_URL
    if not (db_url.startswith("postgresql://") or db_url.startswith("postgresql+psycopg2://")):
        raise RuntimeError(
            f"[FATAL] Invalid DATABASE_URL protocol. Expected PostgreSQL but received: "
            f"{db_url.split('://')[0]}://... SQLite fallback is strictly prohibited."
        )

    return create_engine(
        db_url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        echo=False
    )


engine = create_postgres_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency for providing a transactional database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =========================================================================
# Application Database Models
# =========================================================================

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    preferred_currency = Column(String(10), default="PKR", nullable=False)
    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)

    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    budgets = relationship("Budget", back_populates="user", cascade="all, delete-orphan")
    savings_goals = relationship("SavingsGoal", back_populates="user", cascade="all, delete-orphan")
    memories = relationship("UserMemory", back_populates="user", cascade="all, delete-orphan")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    category = Column(String(100), nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)  # Decimal precision for financial correctness
    type = Column(String(20), nullable=False, default="expense")  # 'expense' or 'income'
    description = Column(TEXT, nullable=True)
    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="transactions")


class Budget(Base):
    __tablename__ = "budgets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    category = Column(String(100), nullable=False, index=True)
    monthly_limit = Column(Numeric(12, 2), nullable=False)
    month = Column(String(7), nullable=False, index=True)  # 'YYYY-MM'
    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="budgets")


class SavingsGoal(Base):
    __tablename__ = "savings_goals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    target_amount = Column(Numeric(12, 2), nullable=False)
    current_amount = Column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    target_date = Column(Date, nullable=True)
    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="savings_goals")


class UserMemory(Base):
    __tablename__ = "user_memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    memory_type = Column(String(50), default="preference", nullable=False)  # 'preference', 'fact', 'habit', 'goal'
    content = Column(TEXT, nullable=False)
    source = Column(String(50), default="conversation", nullable=False)
    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="memories")


class ExpensiveTracker(Base):
    """Legacy table preserved for non-destructive migration."""
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


def init_database() -> None:
    """
    Idempotent database initialization:
    1. Validates PostgreSQL connectivity.
    2. Creates missing tables with indexes and constraints.
    3. Migrates legacy unassigned records if applicable.
    """
    verify_database_connection(engine)
    try:
        Base.metadata.create_all(engine)
        logger.info("[OK] PostgreSQL schema initialized successfully with all models.")
        migrate_legacy_records()
    except SQLAlchemyError as e:
        logger.error(f"[ERROR] Database schema creation failed: {e}")
        raise


def migrate_legacy_records() -> None:
    """Safely migrate legacy rows into transactions if present."""
    db = SessionLocal()
    try:
        # Check if legacy table has data
        has_legacy = False
        try:
            legacy_count = db.query(ExpensiveTracker).count()
            has_legacy = legacy_count > 0
        except Exception:
            return

        tx_count = db.query(Transaction).count()
        if has_legacy and tx_count == 0:
            # Need a user to assign to
            first_user = db.query(User).first()
            if not first_user:
                return

            legacy_records = db.query(ExpensiveTracker).all()
            for rec in legacy_records:
                category_values = {
                    "Education": rec.education,
                    "Travel": rec.travel,
                    "Food": rec.food,
                    "Fruit": rec.fruit,
                    "Medicine": rec.medicine,
                    "Friends": rec.friends,
                }
                for cat, val in category_values.items():
                    if val and val > 0:
                        db.add(
                            Transaction(
                                user_id=first_user.id,
                                date=rec.date,
                                category=cat,
                                amount=Decimal(str(val)),
                                type="expense",
                                description=rec.description or f"Legacy {cat} expense",
                                created_at=rec.created_at or datetime.utcnow(),
                            )
                        )
            db.commit()
            logger.info("[OK] Legacy records migrated safely into Transactions table.")
    except Exception as e:
        db.rollback()
        logger.warning(f"Legacy migration notice: {e}")
    finally:
        db.close()
