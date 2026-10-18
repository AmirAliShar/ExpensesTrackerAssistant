import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

from app.agents.tools import update_transaction_db, delete_transaction_db
from app.database import SessionLocal, Transaction, Budget, SavingsGoal

logger = logging.getLogger("finpilot.confirmation")

# Pending action proposals cache keyed by action_token
_pending_proposals: Dict[str, Dict[str, Any]] = {}
# Index mapping scoped "(user_id, conversation_id)" to active action_token
_thread_to_action_token: Dict[str, str] = {}


def _get_utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_confirmation_proposal(
    user_id: int,
    action_type: str,
    target_id: int,
    summary: str,
    details: Dict[str, Any],
    conversation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create and register a pending confirmation proposal for a destructive action.
    Validates ownership of target record before creating proposal.
    Stores structured information conforming to typed graph state:
    - pending_action
    - action_type
    - target_transaction_id
    - target_transaction_summary
    - confirmation_status
    - conversation_id
    - user_id
    - created_at, expires_at
    """
    session = SessionLocal()
    try:
        record_info = f"Record #{target_id}"
        # Pre-validate ownership of the target resource
        if action_type in ("delete_transaction", "update_transaction"):
            rec = session.query(Transaction).filter(
                Transaction.id == target_id,
                Transaction.user_id == user_id
            ).first()
            if not rec:
                return {
                    "error": f"Transaction #{target_id} not found or not authorized for your account."
                }
            record_info = f"{rec.type.title()}, PKR {float(rec.amount):,.2f}, {rec.category} on {rec.date}"
            details["original_record"] = record_info

        elif action_type in ("delete_budget", "modify_budget"):
            b_rec = session.query(Budget).filter(
                Budget.id == target_id,
                Budget.user_id == user_id
            ).first()
            if not b_rec:
                return {
                    "error": f"Budget #{target_id} not found or not authorized for your account."
                }
            record_info = f"{b_rec.category} limit PKR {float(b_rec.monthly_limit):,.2f}"
            details["original_record"] = record_info

        now = _get_utc_now()
        action_token = f"act_{uuid.uuid4().hex[:12]}"
        proposal = {
            "action_token": action_token,
            "pending_action": action_type,
            "action_type": action_type,
            "target_transaction_id": target_id,
            "target_id": target_id,
            "target_transaction_summary": record_info,
            "summary": summary,
            "details": details,
            "status": "awaiting_confirmation",
            "confirmation_status": "awaiting_confirmation",
            "conversation_id": conversation_id,
            "user_id": user_id,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=15)).isoformat(),
            "_created_at_dt": now,
            "_expires_at_dt": now + timedelta(minutes=15),
        }

        # Clear any prior pending proposal on the same conversation thread
        if conversation_id:
            thread_key = f"{user_id}:{conversation_id}"
            prior_token = _thread_to_action_token.get(thread_key)
            if prior_token and prior_token in _pending_proposals:
                _pending_proposals.pop(prior_token, None)
            _thread_to_action_token[thread_key] = action_token

        _pending_proposals[action_token] = proposal
        logger.info(f"Registered pending confirmation proposal '{action_token}' for user {user_id} on thread {conversation_id}")
        return proposal

    finally:
        session.close()


def get_pending_proposal_for_thread(user_id: int, conversation_id: str) -> Optional[Dict[str, Any]]:
    """Look up active awaiting proposal for a specific user thread."""
    if not conversation_id:
        return None
    thread_key = f"{user_id}:{conversation_id}"
    token = _thread_to_action_token.get(thread_key)
    if not token:
        return None
    proposal = _pending_proposals.get(token)
    if not proposal:
        _thread_to_action_token.pop(thread_key, None)
        return None

    # Check expiration
    expires_dt = proposal.get("_expires_at_dt")
    if expires_dt and _get_utc_now() > expires_dt:
        _pending_proposals.pop(token, None)
        _thread_to_action_token.pop(thread_key, None)
        return None

    if proposal.get("status") != "awaiting_confirmation":
        return None

    return proposal


def clear_pending_proposal_for_thread(user_id: int, conversation_id: str) -> None:
    """Clear pending proposal for a specific user thread."""
    if not conversation_id:
        return
    thread_key = f"{user_id}:{conversation_id}"
    token = _thread_to_action_token.pop(thread_key, None)
    if token:
        _pending_proposals.pop(token, None)


def execute_confirmed_action(
    user_id: int,
    action_token: str,
    confirmed: bool,
) -> Dict[str, Any]:
    """
    Safely resume and execute (or cancel) an interrupted financial operation.
    Validates user ownership, expiration, and prevents duplicate re-execution (idempotency).
    """
    proposal = _pending_proposals.get(action_token)
    if not proposal:
        return {
            "success": False,
            "error": "Confirmation proposal not found or expired. Please submit your request again."
        }

    # Strict multi-user ownership check
    if proposal["user_id"] != user_id:
        return {
            "success": False,
            "error": "Access denied: This confirmation request does not belong to your account."
        }

    # Check expiration
    expires_dt = proposal.get("_expires_at_dt")
    if expires_dt and _get_utc_now() > expires_dt:
        _pending_proposals.pop(action_token, None)
        if proposal.get("conversation_id"):
            clear_pending_proposal_for_thread(user_id, proposal["conversation_id"])
        return {
            "success": False,
            "error": "Confirmation proposal expired (15m window). Please issue the command again."
        }

    # Idempotency check: already executed
    if proposal["status"] != "awaiting_confirmation":
        return {
            "success": False,
            "error": f"This action has already been processed (status: {proposal['status']})."
        }

    # Clean thread map reference
    conv_id = proposal.get("conversation_id")

    # If user explicitly rejects/cancels
    if not confirmed:
        proposal["status"] = "cancelled"
        proposal["confirmation_status"] = "cancelled"
        _pending_proposals.pop(action_token, None)
        if conv_id:
            clear_pending_proposal_for_thread(user_id, conv_id)
        logger.info(f"Proposal '{action_token}' cancelled by user {user_id}.")
        return {
            "success": True,
            "status": "cancelled",
            "message": "Action cancelled. No database changes were made.",
            "action_token": action_token,
        }

    # User confirmed: execute safely inside transaction
    action_type = proposal["action_type"]
    target_id = proposal["target_id"]
    details = proposal["details"]

    try:
        if action_type == "delete_transaction":
            res = delete_transaction_db(user_id=user_id, tx_id=target_id)
            if res.get("success"):
                proposal["status"] = "completed"
                proposal["confirmation_status"] = "completed"
                _pending_proposals.pop(action_token, None)
                if conv_id:
                    clear_pending_proposal_for_thread(user_id, conv_id)
                summary_info = proposal.get("target_transaction_summary", f"Transaction #{target_id}")
                return {
                    "success": True,
                    "status": "completed",
                    "message": f"Transaction #{target_id} ({summary_info}) has been permanently deleted from your records.",
                    "details": res,
                }
            return res

        elif action_type == "update_transaction":
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
                proposal["status"] = "completed"
                proposal["confirmation_status"] = "completed"
                _pending_proposals.pop(action_token, None)
                if conv_id:
                    clear_pending_proposal_for_thread(user_id, conv_id)
                return {
                    "success": True,
                    "status": "completed",
                    "message": f"Confirmed & Updated: Transaction #{target_id} updated successfully.",
                    "details": res,
                }
            return res

        else:
            return {"success": False, "error": f"Unsupported confirmation action type: {action_type}"}

    except Exception as e:
        logger.error(f"Error executing confirmed action '{action_token}': {e}")
        return {"success": False, "error": str(e)}
