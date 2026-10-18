from enum import Enum
from decimal import Decimal
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class IntentType(str, Enum):
    RECORD_TRANSACTION = "record_transaction"
    UPDATE_TRANSACTION = "update_transaction"
    DELETE_TRANSACTION = "delete_transaction"
    GET_SUMMARY = "get_summary"
    LIST_TRANSACTIONS = "list_transactions"
    BUDGET_QUERY = "budget_query"
    SAVE_MEMORY = "save_memory"
    DIRECT_CHAT = "direct_chat"


class IntentClassification(BaseModel):
    intent: IntentType = Field(description="The primary identified financial intent")
    specialist: str = Field(description="Target specialist: expense, budget, analytics, memory, or direct")
    requires_confirmation: bool = Field(default=False, description="Whether action modifies/deletes existing data")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class TransactionProposal(BaseModel):
    action: str = Field(description="Operation type: create, update, or delete")
    target_id: Optional[int] = Field(default=None, description="Existing transaction ID if updating or deleting")
    category: Optional[str] = Field(default=None, description="Expense or income category")
    amount: Optional[Decimal] = Field(default=None, description="Monetary value with decimal precision")
    type: Optional[str] = Field(default="expense", description="'expense' or 'income'")
    date: Optional[str] = Field(default=None, description="Date in YYYY-MM-DD format")
    description: Optional[str] = Field(default=None, description="Description or note")
    requires_confirmation: bool = Field(default=False, description="True for destructive updates or deletions")
    confirmation_summary: Optional[str] = Field(default=None, description="Clear summary for user confirmation")


class BudgetProposal(BaseModel):
    action: str = Field(description="Operation: create, update, delete, or inspect")
    target_id: Optional[int] = None
    category: str
    monthly_limit: Decimal
    month: Optional[str] = None
    requires_confirmation: bool = False
    confirmation_summary: Optional[str] = None


class MemoryExtraction(BaseModel):
    content: str = Field(description="Normalized preference, habit, or rule to remember")
    memory_type: str = Field(default="preference", description="Type: preference, habit, fact, or goal")
    should_save: bool = Field(default=True, description="Whether content represents durable, non-sensitive memory")


class ConfirmationPayload(BaseModel):
    action_token: str
    action_type: str
    target_id: Optional[int] = None
    summary: str
    details: Dict[str, Any]
    status: str = "awaiting_confirmation"  # awaiting_confirmation, confirmed, rejected
