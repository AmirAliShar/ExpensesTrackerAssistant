from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import desc, String, cast
from app.database import Transaction

PALETTE_COLORS = [
    "#6366F1", "#EC4899", "#10B981", "#F59E0B", "#8B5CF6",
    "#3B82F6", "#14B8A6", "#F97316", "#06B6D4", "#84CC16",
    "#D946EF", "#EF4444"
]

def calculate_analytics_summary(
    db: Session,
    user_id: int = 1,
    month: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Dict[str, Any]:
    query = db.query(Transaction).filter(Transaction.user_id == user_id)

    if month:
        query = query.filter(cast(Transaction.date, String).like(f"{month}%"))
    if start_date:
        query = query.filter(Transaction.date >= start_date)
    if end_date:
        query = query.filter(Transaction.date <= end_date)

    transactions = query.order_by(desc(Transaction.date), desc(Transaction.id)).all()

    total_income = sum((t.amount for t in transactions if t.type == "income"), Decimal("0.00"))
    total_expenses = sum((t.amount for t in transactions if t.type == "expense"), Decimal("0.00"))
    net_savings = total_income - total_expenses
    savings_rate = round(float(net_savings / total_income * 100), 1) if total_income > Decimal("0.00") else 0.0

    category_map: Dict[str, Decimal] = {}
    category_counts: Dict[str, int] = {}

    for t in transactions:
        if t.type == "expense":
            cat = t.category.strip().title()
            category_map[cat] = category_map.get(cat, Decimal("0.00")) + t.amount
            category_counts[cat] = category_counts.get(cat, 0) + 1

    pie_items = []
    color_idx = 0
    for cat, amt in sorted(category_map.items(), key=lambda x: x[1], reverse=True):
        pct = round(float(amt / total_expenses * 100), 1) if total_expenses > Decimal("0.00") else 0.0
        pie_items.append({
            "category": cat,
            "amount": round(float(amt), 2),
            "percentage": pct,
            "count": category_counts[cat],
            "color": PALETTE_COLORS[color_idx % len(PALETTE_COLORS)]
        })
        color_idx += 1

    recent = [{
        "id": t.id,
        "user_id": t.user_id,
        "date": str(t.date),
        "category": t.category,
        "amount": float(t.amount),
        "type": t.type,
        "description": t.description,
        "created_at": t.created_at
    } for t in transactions[:8]]

    return {
        "total_income": round(float(total_income), 2),
        "total_expenses": round(float(total_expenses), 2),
        "net_savings": round(float(net_savings), 2),
        "savings_rate": savings_rate,
        "currency": "PKR",
        "categories": pie_items,
        "recent_transactions": recent
    }


def calculate_monthly_report(
    db: Session,
    user_id: int = 1,
    month: Optional[str] = None
) -> Dict[str, Any]:
    curr_month = month or datetime.utcnow().strftime("%Y-%m")
    
    curr_dt = datetime.strptime(f"{curr_month}-01", "%Y-%m-%d")
    prev_dt = (curr_dt - timedelta(days=1)).replace(day=1)
    prev_month = prev_dt.strftime("%Y-%m")

    curr_txs = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        cast(Transaction.date, String).like(f"{curr_month}%")
    ).all()

    prev_txs = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        cast(Transaction.date, String).like(f"{prev_month}%")
    ).all()

    curr_income = sum((t.amount for t in curr_txs if t.type == "income"), Decimal("0.00"))
    curr_expenses = sum((t.amount for t in curr_txs if t.type == "expense"), Decimal("0.00"))
    prev_income = sum((t.amount for t in prev_txs if t.type == "income"), Decimal("0.00"))
    prev_expenses = sum((t.amount for t in prev_txs if t.type == "expense"), Decimal("0.00"))
    
    expense_delta = curr_expenses - prev_expenses
    pct_change = round(float(expense_delta / prev_expenses * 100), 1) if prev_expenses > Decimal("0.00") else 0.0

    cat_spend: Dict[str, Decimal] = {}
    for t in curr_txs:
        if t.type == "expense":
            c = t.category.title()
            cat_spend[c] = cat_spend.get(c, Decimal("0.00")) + t.amount
    
    top_categories = sorted(cat_spend.items(), key=lambda x: x[1], reverse=True)[:3]
    suggestions = []
    if curr_expenses > curr_income and curr_income > Decimal("0.00"):
        suggestions.append("Spending exceeds monthly income. Review non-essential categories.")
    elif curr_income > Decimal("0.00") and (curr_income - curr_expenses) / curr_income > Decimal("0.20"):
        suggestions.append("Excellent savings rate! Consider allocating surplus to long-term goals.")
    if top_categories:
        suggestions.append(f"Largest expenditure category is {top_categories[0][0]} ({float(top_categories[0][1]):,.0f} PKR).")
    if not suggestions:
        if curr_expenses == Decimal("0.00") and curr_income == Decimal("0.00"):
            suggestions.append("No financial activity recorded for this period yet.")
        else:
            suggestions.append("Spending is balanced within current income levels.")

    return {
        "month": curr_month,
        "previous_month": prev_month,
        "total_income": round(float(curr_income), 2),
        "total_expenses": round(float(curr_expenses), 2),
        "net_cash_flow": round(float(curr_income - curr_expenses), 2),
        "expense_delta": round(float(expense_delta), 2),
        "expense_change_vs_last_month": round(float(expense_delta), 2),
        "expense_change_percentage": pct_change,
        "top_categories": [{"category": c, "amount": round(float(a), 2)} for c, a in top_categories],
        "actionable_suggestions": suggestions
    }
