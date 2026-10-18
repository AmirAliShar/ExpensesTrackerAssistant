from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict
from typing import Optional, List, Union, Any, Dict
from datetime import datetime, date as date_type
from decimal import Decimal

# --- Auth Schemas ---
class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    full_name: Optional[str] = None
    preferred_currency: Optional[str] = "PKR"

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: Optional[str] = None
    preferred_currency: str = "PKR"
    created_at: datetime

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut

# --- Transaction Schemas ---
class TransactionCreate(BaseModel):
    date: Union[date_type, str]
    category: str
    amount: float
    type: str = "expense"
    description: Optional[str] = ""

    @field_validator("date", mode="before")
    @classmethod
    def serialize_date(cls, v: Any) -> str:
        if isinstance(v, (date_type, datetime)):
            return v.strftime("%Y-%m-%d")
        return str(v)

class TransactionUpdate(BaseModel):
    date: Optional[Union[date_type, str]] = None
    category: Optional[str] = None
    amount: Optional[float] = None
    type: Optional[str] = None
    description: Optional[str] = None

    @field_validator("date", mode="before")
    @classmethod
    def serialize_date(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        if isinstance(v, (date_type, datetime)):
            return v.strftime("%Y-%m-%d")
        return str(v)

class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    date: Union[date_type, str]
    category: str
    amount: float
    type: str
    description: Optional[str] = None
    created_at: Optional[datetime] = None

    @field_validator("date", mode="before")
    @classmethod
    def serialize_date(cls, v: Any) -> str:
        if isinstance(v, (date_type, datetime)):
            return v.strftime("%Y-%m-%d")
        return str(v)

    @field_validator("amount", mode="before")
    @classmethod
    def serialize_amount(cls, v: Any) -> float:
        if isinstance(v, Decimal):
            return float(v)
        return float(v)

# --- Analytics Schemas ---
class CategoryPieItem(BaseModel):
    category: str
    amount: float
    percentage: float
    count: int
    color: Optional[str] = None

class AnalyticsSummary(BaseModel):
    total_income: float
    total_expenses: float
    net_savings: float
    savings_rate: float
    currency: str = "PKR"
    categories: List[CategoryPieItem]
    recent_transactions: List[TransactionOut]

# --- Budget Schemas ---
class BudgetCreate(BaseModel):
    category: str
    monthly_limit: float
    month: str

class BudgetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    category: str
    monthly_limit: float
    spent: float = 0.0
    utilization_percentage: float = 0.0
    status: str = "safe"
    month: str

    @field_validator("monthly_limit", mode="before")
    @classmethod
    def serialize_limit(cls, v: Any) -> float:
        if isinstance(v, Decimal):
            return float(v)
        return float(v)

# --- Savings Goal Schemas ---
class SavingsGoalCreate(BaseModel):
    title: str
    target_amount: float
    current_amount: Optional[float] = 0.0
    target_date: Optional[Union[date_type, str]] = None

    @field_validator("target_date", mode="before")
    @classmethod
    def serialize_target_date(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        if isinstance(v, (date_type, datetime)):
            return v.strftime("%Y-%m-%d")
        return str(v)

class SavingsGoalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    target_amount: float
    current_amount: float
    progress_percentage: float = 0.0
    target_date: Optional[Union[date_type, str]] = None

    @field_validator("target_date", mode="before")
    @classmethod
    def serialize_target_date(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        if isinstance(v, (date_type, datetime)):
            return v.strftime("%Y-%m-%d")
        return str(v)

    @field_validator("target_amount", "current_amount", mode="before")
    @classmethod
    def serialize_amounts(cls, v: Any) -> float:
        if isinstance(v, Decimal):
            return float(v)
        return float(v)

# --- Memory Schemas ---
class MemoryCreate(BaseModel):
    memory_type: str = "preference"
    content: str
    source: Optional[str] = "user"

class MemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    memory_type: str
    content: str
    source: str
    created_at: datetime
    updated_at: datetime

# --- Agent & Confirmation Schemas ---
class QueryRequest(BaseModel):
    query: str
    thread_id: Optional[str] = None
    is_voice: Optional[bool] = False

class AgentResponse(BaseModel):
    response: str
    spoken_summary: Optional[str] = None
    thread_id: str
    executed_tools: List[str] = []
    memories_used: List[str] = []
    pending_confirmation: Optional[Dict[str, Any]] = None

class ConfirmationActionRequest(BaseModel):
    action_token: str
    confirmed: bool = True

class ConfirmationActionResponse(BaseModel):
    success: bool
    status: str
    message: str
    details: Optional[Dict[str, Any]] = None

class SpeechToTextResponse(BaseModel):
    transcript: str

class MessageHistoryItem(BaseModel):
    id: str
    sender: str
    text: str
    spokenSummary: Optional[str] = None
    toolsUsed: Optional[List[str]] = None
    memoriesUsed: Optional[List[str]] = None
    pendingConfirmation: Optional[Dict[str, Any]] = None
    timestamp: str

class AgentHistoryResponse(BaseModel):
    thread_id: str
    messages: List[MessageHistoryItem] = []
    pending_confirmation: Optional[Dict[str, Any]] = None
