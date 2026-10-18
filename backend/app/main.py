import os
import logging
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.database import (
    init_database,
    verify_database_connection,
    SessionLocal,
    User,
    Transaction,
    Budget,
    SavingsGoal,
    UserMemory,
    engine,
)
from app.auth import get_password_hash, get_current_user
from app.api import router as api_router
from app.api.schemas import QueryRequest
from app.agents.orchestrator import run_finpilot_agent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("finpilot.main")

# Verify PostgreSQL connection and initialize schema
logger.info(f"Starting {settings.APP_NAME} in '{settings.APP_ENV}' mode...")
safe_summary = settings.get_safe_summary()
logger.info(f"Configuration summary: {safe_summary}")

init_database()


def seed_initial_data() -> None:
    """Safely and idempotently seed demo user account if not already present."""
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == "demo@antigravity.io").first()
        if not existing:
            demo_user = User(
                email="demo@antigravity.io",
                hashed_password=get_password_hash("password123"),
                full_name="Demo User",
                preferred_currency="PKR",
                created_at=datetime.utcnow(),
            )
            db.add(demo_user)
            db.commit()
            db.refresh(demo_user)

            if db.query(Transaction).filter(Transaction.user_id == demo_user.id).count() == 0:
                sample_data = [
                    ("Food", Decimal("8500.00"), "expense", "Monthly Groceries & Dining", -2),
                    ("Travel", Decimal("4200.00"), "expense", "Fuel and Taxi Commute", -4),
                    ("Education", Decimal("6000.00"), "expense", "Online Courses & Books", -6),
                    ("Medicine", Decimal("2100.00"), "expense", "Pharmacy & Routine Checkup", -8),
                    ("Fruit", Decimal("1800.00"), "expense", "Fresh Fruits & Markets", -1),
                    ("Friends", Decimal("3500.00"), "expense", "Weekend Dinner with Friends", -3),
                    ("Salary", Decimal("75000.00"), "income", "Monthly Employment Salary", -10),
                    ("Freelance", Decimal("22000.00"), "income", "Software Consulting Client", -5),
                ]
                for cat, amt, t_type, desc_text, day_offset in sample_data:
                    dt = (datetime.utcnow() + timedelta(days=day_offset)).date()
                    db.add(
                        Transaction(
                            user_id=demo_user.id,
                            date=dt,
                            category=cat,
                            amount=amt,
                            type=t_type,
                            description=desc_text,
                            created_at=datetime.utcnow(),
                        )
                    )

                db.add(
                    Budget(
                        user_id=demo_user.id,
                        category="Food",
                        monthly_limit=Decimal("12000.00"),
                        month=datetime.utcnow().strftime("%Y-%m"),
                        created_at=datetime.utcnow(),
                    )
                )
                db.add(
                    Budget(
                        user_id=demo_user.id,
                        category="Overall",
                        monthly_limit=Decimal("40000.00"),
                        month=datetime.utcnow().strftime("%Y-%m"),
                        created_at=datetime.utcnow(),
                    )
                )
                db.add(
                    SavingsGoal(
                        user_id=demo_user.id,
                        title="Emergency Fund",
                        target_amount=Decimal("150000.00"),
                        current_amount=Decimal("45000.00"),
                        created_at=datetime.utcnow(),
                    )
                )
                db.add(
                    UserMemory(
                        user_id=demo_user.id,
                        memory_type="preference",
                        content="Prefers concise bullet-point financial summaries and uses PKR currency.",
                        source="onboarding",
                        created_at=datetime.utcnow(),
                    )
                )
                db.commit()
                logger.info("[OK] Seeded demo initial data for 'demo@antigravity.io'.")
    except Exception as e:
        db.rollback()
        logger.warning(f"Demo seeding note: {e}")
    finally:
        db.close()


seed_initial_data()

app = FastAPI(
    title=f"{settings.APP_NAME} API",
    description="Enterprise-grade Agentic Personal Finance Assistant powered by LangChain, LangGraph, Groq, FastMCP, and PostgreSQL.",
    version="3.0.0",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Modular API Router
app.include_router(api_router, prefix="/api")


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "database": "PostgreSQL",
        "version": "3.0.0",
        "environment": settings.APP_ENV,
    }
