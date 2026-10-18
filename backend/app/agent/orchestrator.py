"""
Backward compatibility bridge for app.agent.orchestrator.
Delegates to the modern app.agents modular architecture.
"""
from typing import Optional, List, Dict, Any

from app.agents.orchestrator import run_finpilot_agent, run_agent
from app.agents.tools import (
    get_user_memories_db,
    save_memory_db,
    record_transaction_db,
    get_financial_summary_db,
    list_recent_transactions_db,
)
from app.memory.checkpointer import get_graph_checkpointer

workflow_checkpointer = get_graph_checkpointer()


def get_user_long_term_memories(user_id: int) -> List[Dict[str, Any]]:
    return get_user_memories_db(user_id)


def save_user_memory_db(user_id: int, content: str, memory_type: str = "preference") -> str:
    res = save_memory_db(user_id, content, memory_type)
    return res.get("message", "Memory saved")


def execute_database_operation(user_id: int, tool_name: str, args: dict) -> dict:
    if tool_name in ["record_transaction", "add_expense"]:
        return record_transaction_db(
            user_id=user_id,
            category=args.get("category", "General"),
            amount=float(args.get("amount", 0.0)),
            type=args.get("type", "expense"),
            date_str=args.get("date"),
            description=args.get("description", ""),
        )
    elif tool_name in ["get_financial_summary", "get_category_breakdown"]:
        return get_financial_summary_db(user_id=user_id, month=args.get("month"))
    elif tool_name == "list_recent_transactions":
        return list_recent_transactions_db(user_id=user_id, limit=int(args.get("limit", 10)))
    elif tool_name == "save_memory":
        return save_memory_db(
            user_id=user_id,
            content=args.get("content", ""),
            memory_type=args.get("memory_type", "preference"),
        )
    return {"success": False, "error": f"Unknown tool: {tool_name}"}


__all__ = [
    "run_agent",
    "run_finpilot_agent",
    "get_user_long_term_memories",
    "save_user_memory_db",
    "execute_database_operation",
    "workflow_checkpointer",
]
