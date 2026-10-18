import logging
from datetime import datetime, date as date_type
from decimal import Decimal
from typing import Dict, Any, List, Optional
from sqlalchemy import desc, String, cast

from app.database import SessionLocal, Transaction, Budget, SavingsGoal, UserMemory
from app.analytics.service import calculate_analytics_summary

logger = logging.getLogger("finpilot.tools")


def record_transaction_db(
    user_id: int,
    category: str,
    amount: float,
    type: str = "expense",
    date_str: Optional[str] = None,
    description: str = "",
) -> Dict[str, Any]:
    """Record a verified income or expense transaction in PostgreSQL."""
    session = SessionLocal()
    try:
        tx_date = datetime.utcnow().date()
        if date_str:
            try:
                tx_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except Exception:
                pass

        dec_amount = Decimal(str(abs(amount))).quantize(Decimal("0.01"))
        clean_category = category.strip().title()
        clean_type = type.lower() if type.lower() in ("income", "expense") else "expense"

        tx = Transaction(
            user_id=user_id,
            date=tx_date,
            category=clean_category,
            amount=dec_amount,
            type=clean_type,
            description=description.strip() or f"{clean_category} {clean_type}",
            created_at=datetime.utcnow(),
        )
        session.add(tx)
        session.commit()
        session.refresh(tx)

        return {
            "success": True,
            "message": f"Recorded {clean_type.title()} of Rs. {float(dec_amount):,.2f} in {clean_category} on {tx.date}.",
            "transaction_id": tx.id,
            "amount": float(dec_amount),
            "category": tx.category,
            "type": tx.type,
            "date": str(tx.date),
        }
    except Exception as e:
        session.rollback()
        logger.error(f"Error recording transaction for user {user_id}: {e}")
        return {"success": False, "error": str(e)}
    finally:
        session.close()


def update_transaction_db(
    user_id: int,
    tx_id: int,
    category: Optional[str] = None,
    amount: Optional[float] = None,
    type: Optional[str] = None,
    date_str: Optional[str] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """Update an existing transaction owned strictly by the authenticated user."""
    session = SessionLocal()
    try:
        tx = session.query(Transaction).filter(
            Transaction.id == tx_id,
            Transaction.user_id == user_id
        ).first()

        if not tx:
            return {
                "success": False,
                "error": f"Transaction #{tx_id} not found or not authorized for this account."
            }

        if category:
            tx.category = category.strip().title()
        if amount is not None:
            tx.amount = Decimal(str(abs(amount))).quantize(Decimal("0.01"))
        if type:
            tx.type = type.lower()
        if description is not None:
            tx.description = description.strip()
        if date_str:
            try:
                tx.date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except Exception:
                pass

        session.commit()
        session.refresh(tx)

        return {
            "success": True,
            "message": f"Successfully updated transaction #{tx.id} to {tx.type.title()} of Rs. {float(tx.amount):,.2f} ({tx.category}).",
            "transaction_id": tx.id,
        }
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating transaction #{tx_id} for user {user_id}: {e}")
        return {"success": False, "error": str(e)}
    finally:
        session.close()


def delete_transaction_db(user_id: int, tx_id: int) -> Dict[str, Any]:
    """Delete a transaction owned strictly by the authenticated user."""
    session = SessionLocal()
    try:
        tx = session.query(Transaction).filter(
            Transaction.id == tx_id,
            Transaction.user_id == user_id
        ).first()

        if not tx:
            return {
                "success": False,
                "error": f"Transaction #{tx_id} not found or not authorized for this account."
            }

        prev_desc = f"{tx.type.title()} Rs. {float(tx.amount):,.2f} ({tx.category}) on {tx.date}"
        session.delete(tx)
        session.commit()

        return {
            "success": True,
            "message": f"Successfully deleted transaction #{tx_id}: {prev_desc}.",
            "transaction_id": tx_id,
        }
    except Exception as e:
        session.rollback()
        logger.error(f"Error deleting transaction #{tx_id} for user {user_id}: {e}")
        return {"success": False, "error": str(e)}
    finally:
        session.close()


def get_financial_summary_db(user_id: int, month: Optional[str] = None) -> Dict[str, Any]:
    """Calculate deterministic financial aggregates for the authenticated user."""
    session = SessionLocal()
    try:
        summary = calculate_analytics_summary(session, user_id=user_id, month=month)
        return {
            "success": True,
            "total_income": summary["total_income"],
            "total_expense": summary["total_expenses"],
            "available_balance": summary["net_savings"],
            "savings_rate": summary["savings_rate"],
            "currency": summary["currency"],
            "categories": summary["categories"],
            "recent_count": len(summary["recent_transactions"]),
        }
    except Exception as e:
        logger.error(f"Error calculating financial summary for user {user_id}: {e}")
        return {"success": False, "error": str(e)}
    finally:
        session.close()


def list_recent_transactions_db(user_id: int, limit: int = 5) -> Dict[str, Any]:
    """Retrieve recent transactions strictly scoped to authenticated user."""
    session = SessionLocal()
    try:
        txs = session.query(Transaction).filter(
            Transaction.user_id == user_id
        ).order_by(desc(Transaction.date), desc(Transaction.id)).limit(limit).all()

        data = [
            {
                "id": t.id,
                "date": str(t.date),
                "category": t.category,
                "amount": float(t.amount),
                "type": t.type,
                "description": t.description,
            }
            for t in txs
        ]
        return {"success": True, "count": len(data), "transactions": data}
    except Exception as e:
        logger.error(f"Error listing transactions for user {user_id}: {e}")
        return {"success": False, "error": str(e)}
    finally:
        session.close()


def get_budget_status_db(user_id: int, month: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve budget utilization and alert thresholds for the user."""
    session = SessionLocal()
    try:
        curr_month = month or datetime.utcnow().strftime("%Y-%m")
        budgets = session.query(Budget).filter(
            Budget.user_id == user_id,
            Budget.month == curr_month
        ).all()

        tx_query = session.query(Transaction).filter(
            Transaction.user_id == user_id,
            Transaction.type == "expense",
            cast(Transaction.date, String).like(f"{curr_month}%")
        ).all()

        total_spent = sum(float(t.amount) for t in tx_query)
        cat_spending = {}
        for t in tx_query:
            cat = t.category.title()
            cat_spending[cat] = cat_spending.get(cat, 0.0) + float(t.amount)

        result_budgets = []
        alerts = []
        for b in budgets:
            limit_val = float(b.monthly_limit)
            spent = total_spent if b.category.lower() == "overall" else cat_spending.get(b.category.title(), 0.0)
            util = round((spent / limit_val * 100.0), 1) if limit_val > 0 else 0.0

            status_flag = "danger" if util >= 100.0 else ("warning" if util >= 80.0 else "safe")
            if status_flag == "danger":
                alerts.append(f"🚨 {b.category} budget exceeded: {spent:,.0f} / {limit_val:,.0f} ({util}%)")
            elif status_flag == "warning":
                alerts.append(f"⚠️ {b.category} budget approaching limit: {spent:,.0f} / {limit_val:,.0f} ({util}%)")

            result_budgets.append({
                "id": b.id,
                "category": b.category,
                "monthly_limit": limit_val,
                "spent": spent,
                "utilization": util,
                "status": status_flag,
            })

        return {
            "success": True,
            "month": curr_month,
            "budgets": result_budgets,
            "alerts": alerts,
            "has_alerts": len(alerts) > 0,
        }
    except Exception as e:
        logger.error(f"Error checking budget status for user {user_id}: {e}")
        return {"success": False, "error": str(e)}
    finally:
        session.close()


def save_memory_db(user_id: int, content: str, memory_type: str = "preference") -> Dict[str, Any]:
    """Save or update permanent user memory preference in PostgreSQL."""
    clean_content = content.strip()
    if not clean_content:
        return {"success": False, "error": "Memory content cannot be empty."}

    session = SessionLocal()
    try:
        existing = session.query(UserMemory).filter(
            UserMemory.user_id == user_id,
            UserMemory.content.ilike(f"%{clean_content}%")
        ).first()

        if existing:
            existing.updated_at = datetime.utcnow()
            session.commit()
            return {"success": True, "message": f"Updated existing memory: {clean_content}"}

        new_mem = UserMemory(
            user_id=user_id,
            memory_type=memory_type,
            content=clean_content,
            source="conversation",
            created_at=datetime.utcnow(),
        )
        session.add(new_mem)
        session.commit()
        return {"success": True, "message": f"Saved preference: {clean_content}"}
    except Exception as e:
        session.rollback()
        logger.error(f"Error saving memory for user {user_id}: {e}")
        return {"success": False, "error": str(e)}
    finally:
        session.close()


def get_user_memories_db(user_id: int) -> List[Dict[str, Any]]:
    """Retrieve all stored durable memories for the authenticated user."""
    session = SessionLocal()
    try:
        mems = session.query(UserMemory).filter(
            UserMemory.user_id == user_id
        ).order_by(desc(UserMemory.updated_at)).all()
        return [{"id": m.id, "type": m.memory_type, "content": m.content} for m in mems]
    except Exception as e:
        logger.error(f"Error fetching memories for user {user_id}: {e}")
        return []
    finally:
        session.close()
