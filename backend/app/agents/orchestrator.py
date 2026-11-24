import re
import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, date as date_type
from decimal import Decimal, InvalidOperation

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from pydantic import BaseModel, Field

from app.core.config import settings
from app.models.factory import ModelFactory, ainvoke_with_fallback, NonRetryableModelError
from app.agents.prompts.loader import get_prompt
from app.memory.checkpointer import get_graph_checkpointer, get_scoped_thread_id
from app.agents.confirmation import (
    create_confirmation_proposal,
    execute_confirmed_action,
    get_pending_proposal_for_thread,
    clear_pending_proposal_for_thread,
)
from app.agents.tools import (
    record_transaction_db,
    update_transaction_db,
    delete_transaction_db,
    get_financial_summary_db,
    list_recent_transactions_db,
    get_budget_status_db,
    save_memory_db,
    get_user_memories_db,
)
from app.database import SessionLocal, Transaction, PersonalLoan
from app.loans.service import (
    LoanConflictError,
    LoanNotFoundError,
    LoanValidationError,
    find_active_loans_for_person,
    get_all_outstanding_loans as query_all_outstanding_loans,
    get_loan_summary as query_loan_summary,
    get_person_loan_history as query_person_loan_history,
    get_person_outstanding_balance as query_person_outstanding_balance,
)
from app.loans.intent import classify_personal_loan_intent, PersonalLoanIntent

logger = logging.getLogger("finpilot.orchestrator")


# =========================================================================
# Pydantic Tool Schemas for Groq / OpenAI Provider Compatibility
# =========================================================================

class record_transaction(BaseModel):
    '''Record a new financial transaction (income or expense) into the verified database.'''
    category: str = Field(description="Category name (e.g. Food, Travel, Salary, Freelance, Education, Shopping)")
    amount: float = Field(description="Transaction amount in user preferred currency (must be positive number)")
    type: str = Field(description="Type of transaction: 'expense' or 'income'")
    date: Optional[str] = Field(default=None, description="Date in YYYY-MM-DD format (defaults to today)")
    description: Optional[str] = Field(default="", description="Descriptive note or merchant details")

class propose_delete(BaseModel):
    '''Propose deleting a transaction with user confirmation safeguard.'''
    transaction_id: int = Field(description="ID of transaction to delete")

class propose_update(BaseModel):
    '''Propose updating a transaction with user confirmation safeguard.'''
    transaction_id: int = Field(description="ID of transaction to update")
    category: Optional[str] = Field(default=None, description="New category name")
    amount: Optional[float] = Field(default=None, description="New amount")
    type: Optional[str] = Field(default=None, description="New type ('expense' or 'income')")
    description: Optional[str] = Field(default=None, description="New description")

class get_financial_summary(BaseModel):
    '''Retrieve user financial aggregates: total income, total expense, available balance, savings rate, categories.'''
    month: Optional[str] = Field(default=None, description="Optional month in YYYY-MM format or null for all time")

class list_recent_transactions(BaseModel):
    '''Retrieve recent transactions from verified database.'''
    limit: Optional[int] = Field(default=5, description="Number of recent records to retrieve")

class check_budget(BaseModel):
    '''Check monthly budget status, category utilization, and active alerts.'''
    month: Optional[str] = Field(default=None, description="Optional month in YYYY-MM format")

class save_memory(BaseModel):
    '''Save a durable user preference or habit to persistent memory.'''
    content: str = Field(description="User preference or habit fact to remember")
    memory_type: Optional[str] = Field(default="preference", description="Type: preference, habit, or goal")

class create_lending_record(BaseModel):
    """Propose recording money lent to another person. This action always requires confirmation."""
    person_name: str = Field(description="Name of the person who borrowed money from the user")
    amount: float = Field(description="Positive amount lent in the user's preferred currency")
    transaction_date: Optional[str] = Field(default=None, description="Date in YYYY-MM-DD format")
    due_date: Optional[str] = Field(default=None, description="Optional repayment due date in YYYY-MM-DD format")
    description: Optional[str] = Field(default=None, description="Optional context for this loan")

class create_borrowing_record(BaseModel):
    """Propose recording money borrowed by the user. This action always requires confirmation."""
    person_name: str = Field(description="Name of the person or people the user borrowed from")
    amount: float = Field(description="Positive amount borrowed in the user's preferred currency")
    transaction_date: Optional[str] = Field(default=None, description="Date in YYYY-MM-DD format")
    due_date: Optional[str] = Field(default=None, description="Optional repayment due date in YYYY-MM-DD format")
    description: Optional[str] = Field(default=None, description="Optional context for this loan")

class record_lending_repayment(BaseModel):
    """Propose recording money received back for a loan previously lent. Confirmation is required."""
    person_name: str = Field(description="Name of the person repaying the user")
    amount: float = Field(description="Positive repayment amount received")
    loan_id: Optional[int] = Field(default=None, description="Specific loan ID when the person has multiple open loans")
    repayment_date: Optional[str] = Field(default=None, description="Date in YYYY-MM-DD format")
    description: Optional[str] = Field(default=None, description="Optional repayment note")

class record_borrowing_repayment(BaseModel):
    """Propose recording money the user returned for a personal loan. Confirmation is required."""
    person_name: str = Field(description="Name of the person the user is repaying")
    amount: float = Field(description="Positive repayment amount returned")
    loan_id: Optional[int] = Field(default=None, description="Specific loan ID when the person has multiple open loans")
    repayment_date: Optional[str] = Field(default=None, description="Date in YYYY-MM-DD format")
    description: Optional[str] = Field(default=None, description="Optional repayment note")

class get_person_loan_history(BaseModel):
    """Retrieve a person's loan records for the authenticated user."""
    person_name: str = Field(description="Person name to search")
    loan_type: Optional[str] = Field(default=None, description="Optional filter: lent or borrowed")

class get_person_outstanding_balance(BaseModel):
    """Calculate outstanding receivables or liabilities for a person."""
    person_name: Optional[str] = Field(default=None, description="Optional person name; omit for all people")
    loan_type: Optional[str] = Field(default=None, description="Optional filter: lent or borrowed")

class get_all_outstanding_loans(BaseModel):
    """List all active or partially repaid loans belonging to the authenticated user."""
    loan_type: Optional[str] = Field(default=None, description="Optional filter: lent or borrowed")

class get_loan_summary(BaseModel):
    """Calculate totals for money lent, borrowed, and outstanding."""
    pass

FINPILOT_TOOLS: List[type[BaseModel]] = [
    record_transaction,
    propose_delete,
    propose_update,
    get_financial_summary,
    list_recent_transactions,
    check_budget,
    save_memory,
    create_lending_record,
    create_borrowing_record,
    record_lending_repayment,
    record_borrowing_repayment,
    get_person_loan_history,
    get_person_outstanding_balance,
    get_all_outstanding_loans,
    get_loan_summary,
]


# =========================================================================
# Checkpoint Helper Utilities
# =========================================================================

def _get_checkpoint_state(scoped_tid: str) -> Dict[str, Any]:
    """Retrieve existing state from PostgreSQL checkpointer for scoped thread ID."""
    cp = get_graph_checkpointer()
    if not cp:
        return {}
    try:
        cfg = {"configurable": {"thread_id": scoped_tid}}
        cp_data = cp.get(cfg)
        if cp_data and "channel_values" in cp_data:
            return cp_data["channel_values"]
    except Exception as e:
        logger.warning(f"Error reading checkpoint for {scoped_tid}: {e}")
    return {}


def _save_checkpoint_state(
    scoped_tid: str,
    messages: List[BaseMessage],
    pending_action: Optional[Dict[str, Any]],
    user_id: int,
    user_currency: str,
) -> None:
    """Save updated conversation messages and pending action directly into checkpointer."""
    cp = get_graph_checkpointer()
    if not cp:
        return
    try:
        cfg = {"configurable": {"thread_id": scoped_tid}}
        # Keep manageable context window: last 30 messages in checkpointer
        trimmed_messages = messages[-30:] if len(messages) > 30 else messages
        
        # Build minimal LangGraph-compatible state dict
        new_values = {
            "messages": trimmed_messages,
            "pending_action": pending_action,
            "user_id": user_id,
            "user_currency": user_currency,
            "thread_id": scoped_tid,
        }
        
        # Save via checkpointer.put if available
        if hasattr(cp, "put"):
            from langgraph.checkpoint.base import empty_checkpoint
            checkpoint = empty_checkpoint()
            checkpoint["channel_values"] = new_values
            metadata = {
                "source": "finpilot_orchestrator",
                "step": len(trimmed_messages),
                "writes": {"channel_values": new_values},
                "parents": {},
            }
            cp.put(cfg, checkpoint, metadata, {})
    except Exception as e:
        logger.warning(f"Error persisting checkpoint for {scoped_tid}: {e}")


def _is_confirmation_query(lower_q: str) -> bool:
    """Detect natural confirmation phrases."""
    clean = re.sub(r"[^\w\s]", "", lower_q).strip()
    exact_matches = {
        "yes", "confirm", "confirmed", "go ahead", "do it", "sure", "yep", "yeah",
        "proceed", "delete it", "yes delete it", "ok delete it", "okay delete it",
        "yes please", "delete", "yes do it", "ok", "okay", "yup", "definitely",
        "yes please delete it", "please delete it"
    }
    if clean in exact_matches:
        return True
    return bool(re.match(r"^(yes|confirm|sure|yep|yeah|ok|okay)\b.*(delete|do it|proceed)?", clean))


def _is_cancellation_query(lower_q: str) -> bool:
    """Detect natural cancellation phrases."""
    clean = re.sub(r"[^\w\s]", "", lower_q).strip()
    exact_matches = {
        "no", "cancel", "cancelled", "dont delete", "dont delete it", "do not delete",
        "stop", "never mind", "nevermind", "abort", "leave it", "keep it", "no thanks"
    }
    if clean in exact_matches:
        return True
    return bool(re.match(r"^(no|cancel|stop)\b.*(delete|nevermind)?", clean))


def _parse_loan_date(value: Optional[str], label: str) -> Optional[date_type]:
    if not value:
        return None
    try:
        return date_type.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise LoanValidationError(f"{label} must use YYYY-MM-DD format.") from exc


def _read_loan_amount(value: Any) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise LoanValidationError("Please provide a valid positive amount.") from exc
    if not amount.is_finite() or amount <= 0 or amount > Decimal("9999999999.99"):
        raise LoanValidationError("Please provide a valid positive amount.")
    rounded = amount.quantize(Decimal("0.01"))
    if rounded != amount:
        raise LoanValidationError("Amounts may have no more than two decimal places.")
    return rounded


def _handle_loan_tool_action(
    action_name: str,
    args: Dict[str, Any],
    user_id: int,
    user_currency: str,
    scoped_tid: str,
) -> Optional[tuple[str, str, Optional[Dict[str, Any]], List[str]]]:
    """Execute read-only loan tools or create a confirmation proposal for loan writes."""
    write_actions = {
        "create_lending_record": ("create_lending_record", "lent"),
        "create_borrowing_record": ("create_borrowing_record", "borrowed"),
        "record_lending_repayment": ("record_lending_repayment", "lent"),
        "record_borrowing_repayment": ("record_borrowing_repayment", "borrowed"),
    }

    try:
        if action_name in write_actions:
            action_type, loan_type = write_actions[action_name]
            person_name = str(args.get("person_name") or "").strip()
            if not person_name:
                return ("Who was the other person in this loan?", "Please specify the person.", None, [])
            amount = _read_loan_amount(args.get("amount"))
            transaction_date = _parse_loan_date(args.get("transaction_date"), "Transaction date")
            due_date = _parse_loan_date(args.get("due_date"), "Due date")
            repayment_date = _parse_loan_date(args.get("repayment_date"), "Repayment date")
            description = str(args.get("description") or "").strip() or None

            if action_name in ("create_lending_record", "create_borrowing_record"):
                details = {
                    "person_name": person_name,
                    "amount": str(amount),
                    "transaction_date": transaction_date.isoformat() if transaction_date else None,
                    "due_date": due_date.isoformat() if due_date else None,
                    "description": description,
                }
                proposal = create_confirmation_proposal(
                    user_id=user_id,
                    action_type=action_type,
                    target_id=0,
                    summary=f"Record {loan_type} loan of {user_currency} {amount:,.2f} with {person_name}",
                    details=details,
                    conversation_id=scoped_tid,
                )
                final = (
                    f"Please confirm: record a **{loan_type}** loan of **{user_currency} {amount:,.2f}** "
                    f"with **{person_name}**. This will be tracked separately from income and expenses."
                )
            else:
                session = SessionLocal()
                try:
                    loan_id = args.get("loan_id")
                    if loan_id is not None:
                        matched = session.query(PersonalLoan).filter(
                            PersonalLoan.id == int(loan_id),
                            PersonalLoan.user_id == user_id,
                            PersonalLoan.loan_type == loan_type,
                            PersonalLoan.status.in_(("active", "partially_paid")),
                        ).all()
                    else:
                        matched = find_active_loans_for_person(session, user_id, person_name, loan_type)
                finally:
                    session.close()

                if not matched:
                    return (
                        f"I couldn't find an outstanding {loan_type} loan for {person_name}. "
                        "Please check the person's name or loan history.",
                        "No matching outstanding loan was found.",
                        None,
                        [action_name],
                    )
                if len(matched) > 1:
                    choices = "\n".join(
                        f"- Loan #{loan.id}: {user_currency} {loan.outstanding_amount:,.2f} outstanding "
                        f"({loan.transaction_date})"
                        for loan in matched
                    )
                    return (
                        f"There are multiple outstanding loans with {person_name}. Which one should this repayment apply to?\n{choices}",
                        "Please choose the loan to apply the repayment to.",
                        None,
                        [action_name],
                    )
                loan = matched[0]
                if amount > loan.outstanding_amount:
                    return (
                        f"The repayment amount exceeds loan #{loan.id}'s outstanding balance of "
                        f"{user_currency} {loan.outstanding_amount:,.2f}.",
                        "Repayment exceeds the outstanding balance.",
                        None,
                        [action_name],
                    )
                details = {
                    "amount": str(amount),
                    "repayment_date": repayment_date.isoformat() if repayment_date else None,
                    "description": description,
                }
                proposal = create_confirmation_proposal(
                    user_id=user_id,
                    action_type=action_type,
                    target_id=loan.id,
                    summary=(
                        f"Record {loan_type} repayment of {user_currency} {amount:,.2f} "
                        f"for loan #{loan.id} with {loan.person_name}"
                    ),
                    details=details,
                    conversation_id=scoped_tid,
                )
                final = (
                    f"Please confirm: record a repayment of **{user_currency} {amount:,.2f}** "
                    f"for loan #{loan.id} with **{loan.person_name}**. "
                    f"Current outstanding balance: {user_currency} {loan.outstanding_amount:,.2f}."
                )
            if "error" in proposal:
                return (f"⚠️ {proposal['error']}", "Loan confirmation could not be created.", None, [])
            return (final, "Please confirm this loan record.", proposal, ["request_confirmation"])

        with SessionLocal() as session:
            if action_name == "get_loan_summary":
                summary = query_loan_summary(session, user_id)
                text = (
                    f"### Personal Loan Summary ({user_currency})\n"
                    f"- Total money lent: {user_currency} {summary['total_lent']:,.2f}\n"
                    f"- Total money borrowed: {user_currency} {summary['total_borrowed']:,.2f}\n"
                    f"- Outstanding receivables: {user_currency} {summary['outstanding_receivables']:,.2f}\n"
                    f"- Outstanding liabilities: {user_currency} {summary['outstanding_liabilities']:,.2f}\n"
                    f"- Pending: {summary['active_count']} · Settled: {summary['settled_count']}"
                )
                return text, "Personal loan summary retrieved.", None, [action_name]

            if action_name == "get_all_outstanding_loans":
                loan_type = args.get("loan_type")
                if loan_type not in (None, "lent", "borrowed"):
                    return ("Use 'lent' or 'borrowed' to filter loans.", "Invalid loan type.", None, [])
                loans = query_all_outstanding_loans(session, user_id, loan_type)
                title = "Outstanding Personal Loans"
                lines = [
                    f"- Loan #{loan.id}: {loan.person_name} · {loan.loan_type} · "
                    f"{user_currency} {loan.outstanding_amount:,.2f} outstanding · {loan.status}"
                    for loan in loans
                ]
                text = f"### {title}\n" + "\n".join(lines) if lines else "You have no outstanding personal loans."
                return text, f"Found {len(loans)} outstanding loans.", None, [action_name]

            if action_name == "get_person_loan_history":
                person_name = str(args.get("person_name") or "").strip()
                if not person_name:
                    return ("Whose loan history would you like to see?", "Please specify a person.", None, [])
                loan_type = args.get("loan_type")
                if loan_type not in (None, "lent", "borrowed"):
                    return ("Use 'lent' or 'borrowed' to filter loan history.", "Invalid loan type.", None, [])
                loans = query_person_loan_history(session, user_id, person_name, loan_type)
                lines = [
                    f"- Loan #{loan.id}: {loan.loan_type} {user_currency} {loan.original_amount:,.2f}, "
                    f"{user_currency} {loan.outstanding_amount:,.2f} outstanding, {loan.status} "
                    f"(recorded {loan.transaction_date})"
                    for loan in loans
                ]
                text = f"### Loan History for {person_name}\n" + "\n".join(lines) if lines else f"No loans recorded for {person_name}."
                return text, f"Found {len(loans)} loan records for {person_name}.", None, [action_name]

            if action_name == "get_person_outstanding_balance":
                person_name = str(args.get("person_name") or "").strip() or None
                loan_type = args.get("loan_type")
                if loan_type not in (None, "lent", "borrowed"):
                    return ("Use 'lent' or 'borrowed' to filter outstanding balances.", "Invalid loan type.", None, [])
                balance = query_person_outstanding_balance(session, user_id, person_name, loan_type)
                scope = f" for {person_name}" if person_name else ""
                text = (
                    f"### Outstanding Balance{scope}\n"
                    f"- Owed to you: {user_currency} {balance['total_receivable']:,.2f}\n"
                    f"- You owe others: {user_currency} {balance['total_liability']:,.2f}"
                )
                return text, "Outstanding personal loan balances retrieved.", None, [action_name]
    except (LoanConflictError, LoanNotFoundError, LoanValidationError) as exc:
        return (f"⚠️ {exc}", str(exc), None, [])

    return None


# =========================================================================
# Main Agent Orchestrator Entrypoint
# =========================================================================

async def run_finpilot_agent(
    query: str,
    thread_id: Optional[str] = None,
    user_id: int = 1,
    user_currency: str = "PKR",
) -> Dict[str, Any]:
    """
    Main entrypoint for FinPilot AI Agentic Financial Assistant.
    Maintains persistent multi-turn conversational memory via LangGraph's PostgreSQL checkpointer.
    Preserves pending actions, enforces user ownership, and interprets confirmations in context.
    """
    # 1. Enforce user-scoped thread ID
    scoped_tid = get_scoped_thread_id(user_id, thread_id)

    # 2. Retrieve user-specific durable memories
    user_memories = get_user_memories_db(user_id)
    memory_context = (
        "\n".join([f"- [{m['type']}] {m['content']}" for m in user_memories])
        if user_memories
        else "No saved user preferences."
    )
    memories_used = [m["content"] for m in user_memories]

    # 3. Restore Checkpointed State from PostgreSQL
    checkpoint_state = _get_checkpoint_state(scoped_tid)
    existing_messages: List[BaseMessage] = list(checkpoint_state.get("messages", []))
    active_pending: Optional[Dict[str, Any]] = checkpoint_state.get("pending_action")
    
    # Also check thread proposals cache for synchronization
    if not active_pending:
        active_pending = get_pending_proposal_for_thread(user_id, scoped_tid)

    clean_query = query.strip()
    lower_q = clean_query.lower()
    executed_tools: List[str] = []
    final_response_text: str = ""
    spoken_summary_text: str = ""
    new_pending_action: Optional[Dict[str, Any]] = None

    # =========================================================================
    # MULTI-TURN STEP 1: Handle Natural Confirmations
    # =========================================================================
    if _is_confirmation_query(lower_q):
        if active_pending and active_pending.get("status") == "awaiting_confirmation":
            action_type = active_pending.get("action_type") or active_pending.get("pending_action")
            target_id = int(active_pending.get("target_transaction_id") or active_pending.get("target_id", 0))

            if action_type == "delete_transaction":
                # Revalidate authenticated user's ownership of the transaction in PostgreSQL
                session = SessionLocal()
                try:
                    tx = session.query(Transaction).filter(
                        Transaction.id == target_id,
                        Transaction.user_id == user_id
                    ).first()

                    if not tx:
                        final_response_text = f"⚠️ Transaction #{target_id} could not be found or was already removed from your records."
                        spoken_summary_text = f"Transaction {target_id} was not found."
                        new_pending_action = None
                        clear_pending_proposal_for_thread(user_id, scoped_tid)
                    else:
                        tx_desc = f"{tx.type.title()} of {user_currency} {float(tx.amount):,.2f} ({tx.category})"
                        session.delete(tx)
                        session.commit()
                        final_response_text = f"Transaction #{target_id} ({tx_desc}) has been deleted successfully."
                        spoken_summary_text = f"Transaction {target_id} deleted successfully."
                        executed_tools.append("delete_transaction")
                        new_pending_action = None
                        clear_pending_proposal_for_thread(user_id, scoped_tid)
                finally:
                    session.close()

            elif action_type == "update_transaction":
                details = active_pending.get("details", {})
                res = update_transaction_db(
                    user_id=user_id,
                    tx_id=target_id,
                    category=details.get("category"),
                    amount=details.get("amount"),
                    type=details.get("type"),
                    date_str=details.get("date"),
                    description=details.get("description"),
                )
                if res.get("success"):
                    final_response_text = f"Transaction #{target_id} has been updated successfully in your records."
                    spoken_summary_text = f"Transaction {target_id} updated successfully."
                    executed_tools.append("update_transaction")
                else:
                    final_response_text = f"⚠️ Could not update Transaction #{target_id}: {res.get('error')}."
                    spoken_summary_text = "Update failed."
                new_pending_action = None
                clear_pending_proposal_for_thread(user_id, scoped_tid)

            elif action_type in {
                "create_lending_record",
                "create_borrowing_record",
                "record_lending_repayment",
                "record_borrowing_repayment",
            }:
                result = execute_confirmed_action(
                    user_id=user_id,
                    action_token=active_pending.get("action_token", ""),
                    confirmed=True,
                )
                final_response_text = result.get("message", "The loan action could not be completed.")
                spoken_summary_text = final_response_text
                if result.get("success"):
                    executed_tools.append(action_type)
                    new_pending_action = None
                else:
                    final_response_text = f"⚠️ {result.get('error', final_response_text)}"
                    new_pending_action = active_pending

            else:
                final_response_text = "Operation confirmed."
                spoken_summary_text = "Action completed."
                new_pending_action = None
                clear_pending_proposal_for_thread(user_id, scoped_tid)

        else:
            # User says 'yes' without a valid pending operation
            final_response_text = "There are no pending operations awaiting your confirmation. How can I help you with your finances today?"
            spoken_summary_text = "No pending operations awaiting confirmation."
            new_pending_action = None

        # Persist conversation turn into checkpointer
        existing_messages.append(HumanMessage(content=clean_query))
        existing_messages.append(AIMessage(content=final_response_text))
        _save_checkpoint_state(scoped_tid, existing_messages, new_pending_action, user_id, user_currency)

        return {
            "response": final_response_text,
            "spoken_summary": spoken_summary_text,
            "thread_id": scoped_tid,
            "executed_tools": executed_tools,
            "memories_used": memories_used,
            "pending_confirmation": new_pending_action,
        }

    # =========================================================================
    # MULTI-TURN STEP 2: Handle Natural Cancellations
    # =========================================================================
    if _is_cancellation_query(lower_q):
        if active_pending and active_pending.get("status") == "awaiting_confirmation":
            target_id = active_pending.get("target_transaction_id") or active_pending.get("target_id")
            final_response_text = f"Action cancelled. Transaction #{target_id} was not deleted and remains unchanged in your records."
            spoken_summary_text = "Action cancelled. No changes were made."
            clear_pending_proposal_for_thread(user_id, scoped_tid)
            new_pending_action = None
        else:
            final_response_text = "Action cancelled. How else can I assist you with your finances today?"
            spoken_summary_text = "Action cancelled."
            new_pending_action = None

        # Persist conversation turn into checkpointer
        existing_messages.append(HumanMessage(content=clean_query))
        existing_messages.append(AIMessage(content=final_response_text))
        _save_checkpoint_state(scoped_tid, existing_messages, new_pending_action, user_id, user_currency)

        return {
            "response": final_response_text,
            "spoken_summary": spoken_summary_text,
            "thread_id": scoped_tid,
            "executed_tools": executed_tools,
            "memories_used": memories_used,
            "pending_confirmation": new_pending_action,
        }

    # =========================================================================
    # MULTI-TURN STEP 3: Handle Explicit Deletion Requests
    # =========================================================================
    del_match = re.search(r"(?:delete|remove)\s+(?:transaction|expense|record)?\s*#?(\d+)", lower_q)
    if del_match:
        tx_id = int(del_match.group(1))
        session = SessionLocal()
        try:
            tx = session.query(Transaction).filter(
                Transaction.id == tx_id,
                Transaction.user_id == user_id
            ).first()

            if not tx:
                final_response_text = f"⚠️ Transaction #{tx_id} not found or not authorized for your account."
                spoken_summary_text = f"Transaction {tx_id} not found."
                new_pending_action = None
            else:
                tx_info = f"{tx.type.title()}, {user_currency} {float(tx.amount):,.2f}, {tx.category} on {tx.date}"
                proposal = create_confirmation_proposal(
                    user_id=user_id,
                    action_type="delete_transaction",
                    target_id=tx_id,
                    summary=f"Delete transaction #{tx_id} ({tx_info})",
                    details={"target_id": tx_id, "original_record": tx_info},
                    conversation_id=scoped_tid,
                )
                final_response_text = (
                    f"I found transaction #{tx_id}: **{tx_info}**.\n\n"
                    f"Do you want to delete it? Say **\"Yes, delete it\"** or click Confirm below."
                )
                spoken_summary_text = f"Found transaction {tx_id}: {tx.category} {tx.type}. Do you want to delete it?"
                new_pending_action = proposal
                executed_tools.append("request_confirmation")
        finally:
            session.close()

        # Persist conversation turn into checkpointer
        existing_messages.append(HumanMessage(content=clean_query))
        existing_messages.append(AIMessage(content=final_response_text))
        _save_checkpoint_state(scoped_tid, existing_messages, new_pending_action, user_id, user_currency)

        return {
            "response": final_response_text,
            "spoken_summary": spoken_summary_text,
            "thread_id": scoped_tid,
            "executed_tools": executed_tools,
            "memories_used": memories_used,
            "pending_confirmation": new_pending_action,
        }

    # Any new active user command supersedes previous pending operations
    if active_pending:
        clear_pending_proposal_for_thread(user_id, scoped_tid)
        new_pending_action = None

    loan_intent = classify_personal_loan_intent(clean_query, existing_messages)
    if loan_intent and loan_intent.action in {"ambiguous_transfer", "gift_expense", "payment_expense"}:
        if loan_intent.action in {"gift_expense", "payment_expense"}:
            res = _handle_offline_loan_intent(
                intent=loan_intent,
                query=clean_query,
                thread_id=scoped_tid,
                user_id=user_id,
                user_currency=user_currency,
                memories_used=memories_used,
            )
            existing_messages.append(HumanMessage(content=clean_query))
            existing_messages.append(AIMessage(content=res["response"]))
            _save_checkpoint_state(scoped_tid, existing_messages, res.get("pending_confirmation"), user_id, user_currency)
            return res

        name = f" to {loan_intent.person_name}" if loan_intent.person_name else ""
        amount_text = (
            f" {user_currency} {loan_intent.amount:,.2f}"
            if loan_intent.amount is not None
            else ""
        )
        final_response_text = (
            f"You mentioned giving{ name}{amount_text}. Was this a loan, a gift, or a payment for something?"
        )
        spoken_summary_text = "Was this a loan, a gift, or a payment?"
        existing_messages.append(HumanMessage(content=clean_query))
        existing_messages.append(AIMessage(content=final_response_text))
        _save_checkpoint_state(scoped_tid, existing_messages, None, user_id, user_currency)
        return {
            "response": final_response_text,
            "spoken_summary": spoken_summary_text,
            "thread_id": scoped_tid,
            "executed_tools": [],
            "memories_used": memories_used,
            "pending_confirmation": None,
        }

    # =========================================================================
    # MULTI-TURN STEP 4: Groq Dynamic Fallback or Rule Fallback Engine
    # =========================================================================
    if not ModelFactory.is_configured():
        res = run_local_offline_orchestrator(
            query=clean_query,
            thread_id=scoped_tid,
            user_id=user_id,
            user_currency=user_currency,
            user_memories=user_memories,
            conversation_messages=existing_messages,
        )
        existing_messages.append(HumanMessage(content=clean_query))
        existing_messages.append(AIMessage(content=res["response"]))
        _save_checkpoint_state(scoped_tid, existing_messages, res.get("pending_confirmation"), user_id, user_currency)
        return res

    # Construct context-engineered prompt with prompt loader
    supervisor_prompt = get_prompt("supervisor")
    voice_prompt = get_prompt("voice")

    system_instruction = f"""{supervisor_prompt}

AUTHENTICATED USER CONTEXT:
- User ID: {user_id}
- Preferred Currency: {user_currency}
- User Durable Memory:
{memory_context}

AVAILABLE ACTIONS:
- record_transaction: Record a new income or expense.
- propose_delete: Deleting an existing transaction requires confirmation!
- propose_update: Updating an existing transaction requires confirmation!
- get_financial_summary: Monthly or overall aggregates.
- list_recent_transactions: Retrieve recent database records.
- check_budget: Monthly budget status.
- save_memory: Save preference fact.
- create_lending_record / create_borrowing_record: Propose a personal loan; never record it before explicit confirmation.
- record_lending_repayment / record_borrowing_repayment: Propose a repayment for an existing loan; never record it before explicit confirmation.
- get_person_loan_history / get_person_outstanding_balance / get_all_outstanding_loans / get_loan_summary: Read verified, user-scoped loan data.

PERSONAL LOAN RULES:
- A loan is a receivable or liability, never a normal income or expense transaction.
- Treat explicit gifts and payments for goods or services as gifts/expenses, not loans.
- If someone says only that they gave money to a person without saying it was a loan, gift, or purchase/payment, ask which it was and do not write a record.
- Use repayments only when the user explicitly says money was returned/received back. Ask which loan when a person has multiple open loans.
- Every loan creation or repayment requires an explicit confirmation proposal.
- Never infer missing names, amounts, dates, or whether the user lent versus borrowed.

VOICE GUIDELINE:
{voice_prompt}
"""

    try:
        # Pass conversation history (last 6 messages) for context retention without token overflow
        prompt_messages: List[BaseMessage] = [SystemMessage(content=system_instruction)]
        if existing_messages:
            prompt_messages.extend(existing_messages[-6:])
        prompt_messages.append(HumanMessage(content=clean_query))

        ai_resp = await ainvoke_with_fallback(prompt_messages, tools=FINPILOT_TOOLS)
        content = ai_resp.content if isinstance(ai_resp.content, str) else str(ai_resp.content)

        action_name = None
        args = {}

        if getattr(ai_resp, "tool_calls", None) and len(ai_resp.tool_calls) > 0:
            tc = ai_resp.tool_calls[0]
            action_name = tc.get("name", "").strip()
            args = tc.get("args", {})
        else:
            action_match = re.search(r"ACTION:\s*([a-zA-Z0-9_]+)", content)
            args_match = re.search(r"ARGS:\s*({.*}|\[.*\])", content, re.DOTALL)
            if action_match:
                action_name = action_match.group(1).strip()
                if args_match:
                    try:
                        args = json.loads(args_match.group(1).strip())
                    except Exception:
                        args = {}

        if action_name == "propose_delete":
            tx_id = int(args.get("transaction_id", 0))
            proposal = create_confirmation_proposal(
                user_id=user_id,
                action_type="delete_transaction",
                target_id=tx_id,
                summary=f"Delete transaction #{tx_id}",
                details={"target_id": tx_id},
                conversation_id=scoped_tid,
            )
            if "error" in proposal:
                final_response_text = f"⚠️ Notice: {proposal['error']}"
                spoken_summary_text = "Notice: Record not found."
                new_pending_action = None
            else:
                orig = proposal.get("target_transaction_summary", f"Transaction #{tx_id}")
                final_response_text = (
                    f"I found transaction #{tx_id}: **{orig}**.\n\n"
                    f"Do you want to delete it? Say **\"Yes, delete it\"** or click Confirm below."
                )
                spoken_summary_text = f"Found transaction {tx_id}. Do you want to delete it?"
                new_pending_action = proposal
                executed_tools.append("request_confirmation")

        elif action_name == "record_transaction":
            amt_val = float(args.get("amount", 0.0))
            if amt_val <= 0:
                final_response_text = "Please specify a valid positive amount to record your transaction."
                spoken_summary_text = "Please specify a positive amount."
            else:
                db_res = record_transaction_db(
                    user_id=user_id,
                    category=args.get("category", "General"),
                    amount=amt_val,
                    type=args.get("type", "expense"),
                    date_str=args.get("date"),
                    description=args.get("description", ""),
                )
                executed_tools.append("record_transaction")
                if db_res.get("success"):
                    tx_cat = db_res.get("category", "General")
                    tx_type = db_res.get("type", "expense").title()
                    tx_date = db_res.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
                    final_response_text = f"Successfully recorded **{tx_type}** of {user_currency} {amt_val:,.2f} under **{tx_cat}** on {tx_date} in your verified database records."
                    spoken_summary_text = f"Recorded {tx_cat} {tx_type.lower()} of {amt_val:.0f} {user_currency}."
                else:
                    final_response_text = f"⚠️ Could not record transaction: {db_res.get('error')}."
                    spoken_summary_text = "Transaction could not be recorded."

        elif action_name == "get_financial_summary":
            db_res = get_financial_summary_db(user_id=user_id, month=args.get("month"))
            executed_tools.append("get_financial_summary")
            top_cat = db_res.get("categories", [{}])[0].get("category", "N/A") if db_res.get("categories") else "N/A"
            final_response_text = (
                f"### Financial Summary ({user_currency})\n"
                f"- **Total Income**: {user_currency} {db_res.get('total_income', 0):,.2f}\n"
                f"- **Total Expenses**: {user_currency} {db_res.get('total_expense', 0):,.2f}\n"
                f"- **Available Balance**: {user_currency} {db_res.get('available_balance', 0):,.2f}\n"
                f"- **Savings Rate**: {db_res.get('savings_rate', 0)}%\n"
                f"- **Top Spending Category**: {top_cat}"
            )
            spoken_summary_text = f"Total expenses are {db_res.get('total_expense', 0):.0f} {user_currency}."

        elif action_name == "list_recent_transactions":
            db_res = list_recent_transactions_db(user_id=user_id, limit=int(args.get("limit", 5)))
            executed_tools.append("list_recent_transactions")
            txs = db_res.get("transactions", [])
            lines = [f"- **#{t['id']}** [{t['date']}] {t['type'].title()} {user_currency} {t['amount']:,.2f} ({t['category']}) - {t['description']}" for t in txs]
            final_response_text = "### Recent Transactions\n" + "\n".join(lines) if lines else "No recent transactions found."
            spoken_summary_text = f"Retrieved {len(txs)} recent transactions."

        elif action_name == "check_budget":
            db_res = get_budget_status_db(user_id=user_id, month=args.get("month"))
            executed_tools.append("check_budget")
            final_response_text = f"### Monthly Budget Status\nTotal Spent: {user_currency} {db_res.get('total_spent', 0):,.2f}"
            spoken_summary_text = "Budget status checked."

        elif action_name == "save_memory":
            save_memory_db(user_id=user_id, content=args.get("content", ""), memory_type=args.get("memory_type", "preference"))
            executed_tools.append("save_memory")
            final_response_text = f"Saved to your durable long-term memory: \"{args.get('content', '')}\""
            spoken_summary_text = "Preference saved."

        elif action_name in {
            "create_lending_record",
            "create_borrowing_record",
            "record_lending_repayment",
            "record_borrowing_repayment",
            "get_person_loan_history",
            "get_person_outstanding_balance",
            "get_all_outstanding_loans",
            "get_loan_summary",
        }:
            result = _handle_loan_tool_action(
                action_name=action_name,
                args=args,
                user_id=user_id,
                user_currency=user_currency,
                scoped_tid=scoped_tid,
            )
            if result:
                final_response_text, spoken_summary_text, new_pending_action, loan_tools = result
                executed_tools.extend(loan_tools)
            else:
                final_response_text = content
                spoken_summary_text = content.split("\n")[0][:100]

        else:
            final_response_text = content
            spoken_summary_text = content.split("\n")[0][:100]

    except NonRetryableModelError:
        res = run_local_offline_orchestrator(
            query=clean_query,
            thread_id=scoped_tid,
            user_id=user_id,
            user_currency=user_currency,
            user_memories=user_memories,
            conversation_messages=existing_messages,
        )
        final_response_text = res["response"]
        spoken_summary_text = res["spoken_summary"]
        executed_tools = res["executed_tools"]
        new_pending_action = res.get("pending_confirmation")
    except Exception as e:
        logger.error(f"Orchestrator error: {e}")
        res = run_local_offline_orchestrator(
            query=clean_query,
            thread_id=scoped_tid,
            user_id=user_id,
            user_currency=user_currency,
            user_memories=user_memories,
            conversation_messages=existing_messages,
        )
        final_response_text = res["response"]
        spoken_summary_text = res["spoken_summary"]
        executed_tools = res["executed_tools"]
        new_pending_action = res.get("pending_confirmation")

    # Persist updated turn into checkpointer
    existing_messages.append(HumanMessage(content=clean_query))
    existing_messages.append(AIMessage(content=final_response_text))
    _save_checkpoint_state(scoped_tid, existing_messages, new_pending_action, user_id, user_currency)

    return {
        "response": final_response_text,
        "spoken_summary": spoken_summary_text,
        "thread_id": scoped_tid,
        "executed_tools": executed_tools,
        "memories_used": memories_used,
        "pending_confirmation": new_pending_action,
    }


def _handle_offline_loan_intent(
    *,
    intent: PersonalLoanIntent,
    query: str,
    thread_id: str,
    user_id: int,
    user_currency: str,
    memories_used: List[str],
) -> Dict[str, Any]:
    """Route recognized loan requests through the same scoped services and confirmation proposals."""
    if intent.action in {"gift_expense", "payment_expense"}:
        if intent.amount is None:
            response = "What amount should I record for this gift or payment?"
            return {
                "response": response,
                "spoken_summary": "Please specify the amount.",
                "thread_id": thread_id,
                "executed_tools": [],
                "memories_used": memories_used,
                "pending_confirmation": None,
            }
        category = "Gift" if intent.action == "gift_expense" else "Other"
        result = record_transaction_db(
            user_id=user_id,
            category=category,
            amount=float(intent.amount),
            type="expense",
            date_str=intent.transaction_date.isoformat() if intent.transaction_date else None,
            description=query,
        )
        if not result.get("success"):
            response = f"⚠️ Could not record this {category.lower()} expense: {result.get('error', 'Database error')}."
            spoken = "Expense could not be recorded."
        else:
            response = (
                f"Recorded this as a **{category.lower()} expense**, not a loan: "
                f"{user_currency} {intent.amount:,.2f}."
            )
            spoken = f"Recorded a {category.lower()} expense of {intent.amount:.2f} {user_currency}."
        return {
            "response": response,
            "spoken_summary": spoken,
            "thread_id": thread_id,
            "executed_tools": ["record_transaction"],
            "memories_used": memories_used,
            "pending_confirmation": None,
        }

    action_tools = {
        "create_lending": "create_lending_record",
        "create_borrowing": "create_borrowing_record",
        "repayment_lending": "record_lending_repayment",
        "repayment_borrowing": "record_borrowing_repayment",
        "history": "get_person_loan_history",
        "balance": "get_person_outstanding_balance",
        "outstanding": "get_all_outstanding_loans",
        "summary": "get_loan_summary",
    }

    if intent.action == "ambiguous_transfer":
        name = f" to {intent.person_name}" if intent.person_name else ""
        amount = f" {user_currency} {intent.amount:,.2f}" if intent.amount is not None else ""
        response = f"You mentioned giving{name}{amount}. Was this a loan, a gift, or a payment for something?"
        return {
            "response": response,
            "spoken_summary": "Was this a loan, a gift, or a payment?",
            "thread_id": thread_id,
            "executed_tools": [],
            "memories_used": memories_used,
            "pending_confirmation": None,
        }

    if intent.action in {"create_lending", "create_borrowing", "repayment_lending", "repayment_borrowing"}:
        if not intent.person_name:
            response = "Who was the other person in this loan or repayment?"
            return {
                "response": response,
                "spoken_summary": "Please specify the person.",
                "thread_id": thread_id,
                "executed_tools": [],
                "memories_used": memories_used,
                "pending_confirmation": None,
            }
        if intent.amount is None:
            response = f"What amount should I record for {intent.person_name}?"
            return {
                "response": response,
                "spoken_summary": "Please specify the amount.",
                "thread_id": thread_id,
                "executed_tools": [],
                "memories_used": memories_used,
                "pending_confirmation": None,
            }

    action_name = action_tools.get(intent.action)
    if not action_name:
        return {
            "response": "I couldn't determine the personal loan action. Please clarify whether this is lending, borrowing, or repayment.",
            "spoken_summary": "Please clarify the loan action.",
            "thread_id": thread_id,
            "executed_tools": [],
            "memories_used": memories_used,
            "pending_confirmation": None,
        }

    args: Dict[str, Any] = {
        "person_name": intent.person_name,
        "amount": str(intent.amount) if intent.amount is not None else None,
        "loan_type": intent.loan_type,
        "transaction_date": intent.transaction_date.isoformat() if intent.transaction_date else None,
        "repayment_date": intent.transaction_date.isoformat() if intent.transaction_date else None,
        "due_date": intent.due_date.isoformat() if intent.due_date else None,
    }
    result = _handle_loan_tool_action(action_name, args, user_id, user_currency, thread_id)
    if result is None:
        response = "I couldn't complete that personal loan request."
        spoken = response
        pending = None
        tools: List[str] = []
    else:
        response, spoken, pending, tools = result
    return {
        "response": response,
        "spoken_summary": spoken,
        "thread_id": thread_id,
        "executed_tools": tools,
        "memories_used": memories_used,
        "pending_confirmation": pending,
    }


def run_local_offline_orchestrator(
    query: str,
    thread_id: str,
    user_id: int,
    user_currency: str,
    user_memories: List[Dict[str, Any]],
    note: Optional[str] = None,
    conversation_messages: Optional[List[BaseMessage]] = None,
) -> Dict[str, Any]:
    """
    Deterministic rule-based offline fallback engine.
    Ensures uninterrupted financial operations even during complete network or API outages.
    """
    lower_q = query.lower().strip()
    executed_tools = []
    memories_used = [m["content"] for m in user_memories]

    loan_intent = classify_personal_loan_intent(query, conversation_messages or [])
    if loan_intent:
        return _handle_offline_loan_intent(
            intent=loan_intent,
            query=query,
            thread_id=thread_id,
            user_id=user_id,
            user_currency=user_currency,
            memories_used=memories_used,
        )

    # 1. Check for Memory intent
    if any(k in lower_q for k in ["remember", "prefer", "note that", "save preference", "habit"]):
        clean_content = re.sub(
            r"^(please\s+)?(remember\s+that\s+|remember\s+|note\s+that\s+|save\s+preference\s+|save\s+)",
            "",
            query,
            flags=re.I,
        ).strip()
        save_memory_db(user_id, clean_content, "preference")
        executed_tools.append("save_memory")
        return {
            "response": f"Saved to your durable long-term memory: \"{clean_content}\"",
            "spoken_summary": f"Remembered: {clean_content[:60]}",
            "thread_id": thread_id,
            "executed_tools": executed_tools,
            "memories_used": memories_used,
            "pending_confirmation": None,
        }

    # 2. Check for Financial Inquiries
    is_inquiry = any(q_word in lower_q for q_word in ["what", "how much", "how many", "show", "tell me", "list", "check", "view"])

    # Recent Transactions inquiry
    if is_inquiry and any(k in lower_q for k in ["recent", "transactions", "history", "logs", "activity"]):
        tx_data = list_recent_transactions_db(user_id=user_id, limit=5)
        executed_tools.append("list_recent_transactions")
        tx_list = tx_data.get("transactions", [])
        if not tx_list:
            resp_text = "You do not have any recorded transactions yet."
        else:
            lines = [f"- **#{t['id']}** [{t['date']}] {t['type'].title()} {user_currency} {t['amount']:,.2f} ({t['category']}) - {t['description']}" for t in tx_list]
            resp_text = "### Recent Verified Transactions\n" + "\n".join(lines)
        return {
            "response": resp_text,
            "spoken_summary": f"Retrieved {len(tx_list)} recent transactions.",
            "thread_id": thread_id,
            "executed_tools": executed_tools,
            "memories_used": memories_used,
            "pending_confirmation": None,
        }

    # Top Category / Largest Spending inquiry
    if any(k in lower_q for k in ["largest", "top", "highest", "biggest"]) and ("category" in lower_q or "expense" in lower_q or "spend" in lower_q):
        summary = get_financial_summary_db(user_id=user_id)
        executed_tools.append("get_financial_summary")
        categories = summary.get("categories", [])
        if categories:
            top = categories[0]
            resp_text = (
                f"Your largest expenditure category is **{top['category']}** with "
                f"**{user_currency} {top['amount']:,.2f}** ({top['percentage']}% of total expenses)."
            )
            spoken = f"Your top spending category is {top['category']} at {top['amount']:.0f} {user_currency}."
        else:
            resp_text = "You do not have any recorded expenses for this period yet."
            spoken = "No recorded expenses found."
        return {
            "response": resp_text,
            "spoken_summary": spoken,
            "thread_id": thread_id,
            "executed_tools": executed_tools,
            "memories_used": memories_used,
            "pending_confirmation": None,
        }

    # 3. Check for Explicit Transaction Recording Intent
    record_signals = ["add", "spent", "paid", "bought", "record", "log", "received", "earned", "got paid", "salary", "freelance"]
    is_recording = (not is_inquiry) and any(sig in lower_q for sig in record_signals)

    if is_recording:
        raw_numbers = re.findall(r"[\d,]+(?:\.\d+)?", query)
        if not raw_numbers:
            return {
                "response": f"Please specify the amount you would like to record (e.g. *'Add {user_currency} 500 for Food'*).",
                "spoken_summary": "Please specify the transaction amount.",
                "thread_id": thread_id,
                "executed_tools": [],
                "memories_used": memories_used,
                "pending_confirmation": None,
            }

        clean_num = raw_numbers[0].replace(",", "")
        try:
            amt = float(clean_num)
        except Exception:
            amt = 0.0

        if amt <= 0:
            return {
                "response": "Please specify a valid positive amount to record your transaction.",
                "spoken_summary": "Please specify a positive amount.",
                "thread_id": thread_id,
                "executed_tools": [],
                "memories_used": memories_used,
                "pending_confirmation": None,
            }

        income_signals = ["salary", "freelance", "income", "earned", "received", "bonus", "profit", "gift", "dividend", "got paid"]
        is_income = any(sig in lower_q for sig in income_signals)
        t_type = "income" if is_income else "expense"

        if is_income:
            if "salary" in lower_q: cat = "Salary"
            elif "freelance" in lower_q or "client" in lower_q: cat = "Freelance"
            elif "invest" in lower_q or "dividend" in lower_q or "stock" in lower_q: cat = "Investment"
            elif "business" in lower_q: cat = "Business"
            elif "bonus" in lower_q: cat = "Bonus"
            elif "gift" in lower_q: cat = "Gift"
            else: cat = "Other"
        else:
            if any(w in lower_q for w in ["food", "lunch", "dinner", "breakfast", "meal", "coffee", "tea", "restaurant", "snack", "eat", "cafe", "burger"]): cat = "Food"
            elif any(w in lower_q for w in ["travel", "fuel", "petrol", "cab", "uber", "careem", "commute", "taxi", "bus", "train", "flight"]): cat = "Travel"
            elif any(w in lower_q for w in ["education", "course", "book", "books", "tuition", "school", "college", "fee", "study"]): cat = "Education"
            elif any(w in lower_q for w in ["medicine", "doctor", "pharmacy", "medical", "hospital", "clinic", "health", "pills"]): cat = "Medicine"
            elif any(w in lower_q for w in ["rent", "landlord", "apartment"]): cat = "Rent"
            elif any(w in lower_q for w in ["utility", "utilities", "electricity", "water", "gas", "bill", "wifi", "internet"]): cat = "Utilities"
            elif any(w in lower_q for w in ["fruit", "fruits", "grocery", "groceries", "vegetable", "vegetables", "market"]): cat = "Fruit"
            elif any(w in lower_q for w in ["friend", "friends", "hangout", "party", "social"]): cat = "Friends"
            elif any(w in lower_q for w in ["shopping", "clothes", "shoes", "mall", "cloth", "dress"]): cat = "Shopping"
            elif any(w in lower_q for w in ["movie", "cinema", "game", "gaming", "netflix", "entertainment"]): cat = "Entertainment"
            else: cat = "Other"

        res = record_transaction_db(
            user_id=user_id,
            category=cat,
            amount=amt,
            type=t_type,
            description=query,
        )
        executed_tools.append("record_transaction")

        if not res.get("success"):
            return {
                "response": f"⚠️ Could not save transaction to database: {res.get('error', 'Database error')}.",
                "spoken_summary": "Transaction could not be saved to your records.",
                "thread_id": thread_id,
                "executed_tools": executed_tools,
                "memories_used": memories_used,
                "pending_confirmation": None,
            }

        tx_date = res.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        resp_text = f"Successfully recorded **{t_type.title()}** of {user_currency} {amt:,.2f} under **{cat}** on {tx_date} in your verified database records."
        return {
            "response": resp_text,
            "spoken_summary": f"Recorded {cat} {t_type} of {amt:.0f} {user_currency}.",
            "thread_id": thread_id,
            "executed_tools": executed_tools,
            "memories_used": memories_used,
            "pending_confirmation": None,
        }

    # 4. Default / Financial Summary
    summary = get_financial_summary_db(user_id=user_id)
    executed_tools.append("get_financial_summary")
    top_cat = summary["categories"][0]["category"] if summary.get("categories") else "N/A"
    ans = (
        f"### Financial Summary ({user_currency})\n"
        f"- **Total Income**: {user_currency} {summary.get('total_income', 0):,.2f}\n"
        f"- **Total Expenses**: {user_currency} {summary.get('total_expense', 0):,.2f}\n"
        f"- **Available Balance**: {user_currency} {summary.get('available_balance', 0):,.2f}\n"
        f"- **Savings Rate**: {summary.get('savings_rate', 0)}%\n"
        f"- **Top Spending Category**: {top_cat}"
    )
    return {
        "response": ans,
        "spoken_summary": f"Total expenses are {summary.get('total_expense', 0):.0f} {user_currency} with available balance of {summary.get('available_balance', 0):.0f} {user_currency}.",
        "thread_id": thread_id,
        "executed_tools": executed_tools,
        "memories_used": memories_used,
        "pending_confirmation": None,
    }


# Backward-compatible alias
async def run_agent(
    query: str,
    thread_id: Optional[str] = None,
    user_id: int = 1,
    user_currency: str = "PKR",
) -> Dict[str, Any]:
    return await run_finpilot_agent(
        query=query,
        thread_id=thread_id,
        user_id=user_id,
        user_currency=user_currency,
    )
