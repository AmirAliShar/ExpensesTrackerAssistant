from typing import Optional
from decimal import Decimal
from datetime import datetime
from fastmcp import FastMCP
from sqlalchemy.orm import sessionmaker
from sqlalchemy import String, cast, desc

from app.database import engine, init_database, Transaction, ExpensiveTracker, UserMemory
from app.agents.tools import record_transaction_db, save_memory_db

mcp = FastMCP(name="FinPilotMCP")
Session = sessionmaker(bind=engine)


@mcp.tool(name="add_expense", description="Add a new monthly expense record to the database.")
def InsertItem(
    date: str,
    education: int = 0,
    travel: int = 0,
    food: int = 0,
    fruit: int = 0,
    medicine: int = 0,
    friends: int = 0,
    description: str = "",
    user_id: Optional[int] = None,
):
    """Add multi-category expense items into the database."""
    session = Session()
    try:
        parsed_date = datetime.strptime(date, "%Y-%m-%d").date() if isinstance(date, str) and "-" in date else date
        new_record = ExpensiveTracker(
            date=parsed_date,
            education=education,
            travel=travel,
            food=food,
            fruit=fruit,
            medicine=medicine,
            friends=friends,
            description=description,
            created_at=datetime.utcnow(),
        )
        session.add(new_record)

        categories = {
            "Education": education,
            "Travel": travel,
            "Food": food,
            "Fruit": fruit,
            "Medicine": medicine,
            "Friends": friends,
        }
        target_user_id = user_id or 1
        for cat, val in categories.items():
            if val and val > 0:
                tx = Transaction(
                    user_id=target_user_id,
                    date=new_record.date,
                    category=cat,
                    amount=Decimal(str(val)),
                    type="expense",
                    description=description or f"{cat} expense",
                    created_at=datetime.utcnow(),
                )
                session.add(tx)

        session.commit()
        return {"status": "success", "message": "Expense added successfully."}
    except Exception as e:
        session.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        session.close()


add_expense = InsertItem


@mcp.tool(name="record_transaction", description="Add a single categorized income or expense transaction.")
def record_transaction(
    user_id: int,
    category: str,
    amount: float,
    type: str = "expense",
    date_str: Optional[str] = None,
    description: str = "",
):
    """Securely record an authenticated financial transaction."""
    res = record_transaction_db(
        user_id=user_id,
        category=category,
        amount=amount,
        type=type,
        date_str=date_str,
        description=description,
    )
    if res.get("success"):
        return {"status": "success", "message": res.get("message"), "transaction_id": res.get("transaction_id")}
    return {"status": "error", "message": res.get("error", "Failed to record transaction")}


@mcp.tool(name="get_expenses_record", description="Fetch expense data by month or specific category.")
def get_expenses_record(user_id: int, month: Optional[str] = None, category: Optional[str] = None):
    """Fetch expense records strictly scoped to the authenticated user."""
    session = Session()
    try:
        query = session.query(Transaction).filter(Transaction.user_id == user_id)
        if month:
            query = query.filter(cast(Transaction.date, String).like(f"{month}%"))
        if category:
            query = query.filter(Transaction.category.ilike(f"%{category}%"))

        transactions = query.order_by(desc(Transaction.date)).all()
        data = []
        total_amount = Decimal("0.00")
        for tx in transactions:
            data.append({
                "id": tx.id,
                "date": tx.date.strftime("%Y-%m-%d"),
                "category": tx.category,
                "amount": float(tx.amount),
                "type": tx.type,
                "description": tx.description,
            })
            if tx.type == "expense":
                total_amount += tx.amount

        return {
            "status": "success",
            "count": len(data),
            "total_expense": float(total_amount),
            "data": data,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        session.close()


@mcp.tool(name="save_user_memory", description="Save a permanent preference or financial habit to user's durable memory.")
def save_user_memory(user_id: int, content: str, memory_type: str = "preference"):
    res = save_memory_db(user_id=user_id, content=content, memory_type=memory_type)
    if res.get("success"):
        return {"status": "success", "message": res.get("message")}
    return {"status": "error", "message": res.get("error")}


__all__ = [
    "mcp",
    "InsertItem",
    "add_expense",
    "record_transaction",
    "get_expenses_record",
    "save_user_memory",
]

if __name__ == "__main__":
    init_database()
    mcp.run(transport="streamable-http", port=8001)
