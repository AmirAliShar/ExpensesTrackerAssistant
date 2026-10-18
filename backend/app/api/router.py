import os
import io
import csv
from datetime import datetime, timedelta
from typing import List, Optional
from decimal import Decimal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Response,
    UploadFile,
    File,
    Query,
)
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, String, cast

from app.database import (
    get_db,
    User,
    Transaction,
    Budget,
    SavingsGoal,
    UserMemory,
)
from app.auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    get_current_user,
    get_optional_current_user,
    normalize_email,
    verify_user_ownership,
)
from app.analytics import (
    calculate_analytics_summary,
    calculate_monthly_report,
)
from app.agents.orchestrator import run_finpilot_agent
from app.agents.confirmation import execute_confirmed_action
from app.voice.stt import transcribe_audio_groq
from app.voice.tts import synthesize_speech
from app.api.schemas import (
    UserRegister,
    UserLogin,
    TokenResponse,
    UserOut,
    TransactionCreate,
    TransactionUpdate,
    TransactionOut,
    AnalyticsSummary,
    BudgetCreate,
    BudgetOut,
    SavingsGoalCreate,
    SavingsGoalOut,
    QueryRequest,
    AgentResponse,
    MemoryCreate,
    MemoryOut,
    ConfirmationActionRequest,
    ConfirmationActionResponse,
    SpeechToTextResponse,
    AgentHistoryResponse,
    MessageHistoryItem,
)

router = APIRouter()


# --- Auth Routes ---
@router.post("/auth/register", response_model=TokenResponse)
def register(user_in: UserRegister, db: Session = Depends(get_db)):
    clean_email = normalize_email(user_in.email)
    existing = db.query(User).filter(User.email == clean_email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists."
        )

    hashed_pwd = get_password_hash(user_in.password)
    new_user = User(
        email=clean_email,
        hashed_password=hashed_pwd,
        full_name=user_in.full_name or clean_email.split("@")[0].title(),
        preferred_currency=user_in.preferred_currency or "PKR",
        created_at=datetime.utcnow(),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    token = create_access_token(data={"sub": str(new_user.id), "email": new_user.email})
    return TokenResponse(access_token=token, token_type="bearer", user=UserOut.from_orm(new_user))


@router.post("/auth/login", response_model=TokenResponse)
def login(user_in: UserLogin, db: Session = Depends(get_db)):
    clean_email = normalize_email(user_in.email)
    user = db.query(User).filter(User.email == clean_email).first()
    if not user or not verify_password(user_in.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password."
        )
    token = create_access_token(data={"sub": str(user.id), "email": user.email})
    return TokenResponse(access_token=token, token_type="bearer", user=UserOut.from_orm(user))


@router.get("/auth/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return UserOut.from_orm(current_user)


# --- Transactions CRUD (Strict Multi-User Isolation) ---
@router.get("/transactions", response_model=List[TransactionOut])
def get_transactions(
    category: Optional[str] = None,
    month: Optional[str] = None,
    type: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Transaction).filter(Transaction.user_id == current_user.id)

    if category and category != "All":
        query = query.filter(Transaction.category.ilike(f"%{category}%"))
    if month:
        query = query.filter(cast(Transaction.date, String).like(f"{month}%"))
    if type and type != "all":
        query = query.filter(Transaction.type == type.lower())

    txs = query.order_by(desc(Transaction.date), desc(Transaction.id)).limit(limit).all()
    return [TransactionOut.from_orm(t) for t in txs]


@router.post("/transactions", response_model=TransactionOut)
def create_transaction(
    tx_in: TransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        tx_date = datetime.strptime(str(tx_in.date), "%Y-%m-%d").date()
    except Exception:
        tx_date = datetime.utcnow().date()

    dec_amount = Decimal(str(abs(tx_in.amount))).quantize(Decimal("0.01"))

    tx = Transaction(
        user_id=current_user.id,
        date=tx_date,
        category=tx_in.category.strip().title(),
        amount=dec_amount,
        type=tx_in.type.lower(),
        description=tx_in.description or f"{tx_in.category} {tx_in.type}",
        created_at=datetime.utcnow(),
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return TransactionOut.from_orm(tx)


@router.put("/transactions/{tx_id}", response_model=TransactionOut)
def update_transaction(
    tx_id: int,
    tx_update: TransactionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tx = db.query(Transaction).filter(
        Transaction.id == tx_id,
        Transaction.user_id == current_user.id,
    ).first()

    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found or access denied."
        )

    if tx_update.category:
        tx.category = tx_update.category.strip().title()
    if tx_update.amount is not None:
        tx.amount = Decimal(str(abs(tx_update.amount))).quantize(Decimal("0.01"))
    if tx_update.type:
        tx.type = tx_update.type.lower()
    if tx_update.description is not None:
        tx.description = tx_update.description
    if tx_update.date:
        try:
            tx.date = datetime.strptime(str(tx_update.date), "%Y-%m-%d").date()
        except Exception:
            pass

    db.commit()
    db.refresh(tx)
    return TransactionOut.from_orm(tx)


@router.delete("/transactions/{tx_id}")
def delete_transaction(
    tx_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tx = db.query(Transaction).filter(
        Transaction.id == tx_id,
        Transaction.user_id == current_user.id,
    ).first()

    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found or access denied."
        )

    db.delete(tx)
    db.commit()
    return {"status": "success", "message": f"Transaction {tx_id} deleted."}


# --- Analytics & Reports ---
@router.get("/analytics/summary", response_model=AnalyticsSummary)
def get_analytics(
    month: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    summary = calculate_analytics_summary(
        db,
        user_id=current_user.id,
        month=month,
        start_date=start_date,
        end_date=end_date,
    )
    return summary


@router.get("/reports/csv")
def export_csv(
    month: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Transaction).filter(Transaction.user_id == current_user.id)
    if month:
        query = query.filter(cast(Transaction.date, String).like(f"{month}%"))
    txs = query.order_by(desc(Transaction.date)).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Date", "Category", "Type", f"Amount ({current_user.preferred_currency})", "Description"])
    for t in txs:
        writer.writerow([t.id, str(t.date), t.category, t.type, float(t.amount), t.description or ""])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=expenses_{month or 'all'}.csv"},
    )


@router.get("/reports/monthly")
def get_monthly_report(
    month: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return calculate_monthly_report(db, user_id=current_user.id, month=month)


# --- Budgets & Goals ---
@router.get("/budgets", response_model=List[BudgetOut])
def get_budgets(
    month: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    curr_month = month or datetime.utcnow().strftime("%Y-%m")
    budgets = db.query(Budget).filter(Budget.user_id == current_user.id).all()

    tx_query = db.query(Transaction).filter(
        Transaction.user_id == current_user.id,
        Transaction.type == "expense",
        cast(Transaction.date, String).like(f"{curr_month}%"),
    ).all()

    total_expense = sum(float(t.amount) for t in tx_query)
    cat_spending = {}
    for t in tx_query:
        cat_spending[t.category.title()] = cat_spending.get(t.category.title(), 0.0) + float(t.amount)

    res = []
    for b in budgets:
        limit_val = float(b.monthly_limit)
        spent = total_expense if b.category.lower() == "overall" else cat_spending.get(b.category.title(), 0.0)
        util = round((spent / limit_val * 100.0), 1) if limit_val > 0 else 0.0
        status_flag = "danger" if util >= 100 else ("warning" if util >= 80 else "safe")
        res.append(BudgetOut(
            id=b.id,
            user_id=b.user_id,
            category=b.category,
            monthly_limit=limit_val,
            spent=spent,
            utilization_percentage=util,
            status=status_flag,
            month=b.month,
        ))
    return res


@router.post("/budgets", response_model=BudgetOut)
def create_budget(
    b_in: BudgetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dec_limit = Decimal(str(abs(b_in.monthly_limit))).quantize(Decimal("0.01"))
    b = Budget(
        user_id=current_user.id,
        category=b_in.category.strip().title(),
        monthly_limit=dec_limit,
        month=b_in.month,
        created_at=datetime.utcnow(),
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    return BudgetOut(
        id=b.id,
        user_id=b.user_id,
        category=b.category,
        monthly_limit=float(b.monthly_limit),
        spent=0.0,
        utilization_percentage=0.0,
        status="safe",
        month=b.month,
    )


@router.delete("/budgets/{budget_id}")
def delete_budget(
    budget_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    b = db.query(Budget).filter(Budget.id == budget_id, Budget.user_id == current_user.id).first()
    if not b:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")
    db.delete(b)
    db.commit()
    return {"status": "success", "message": "Budget deleted"}


@router.get("/goals", response_model=List[SavingsGoalOut])
def get_goals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    goals = db.query(SavingsGoal).filter(SavingsGoal.user_id == current_user.id).all()
    res = []
    for g in goals:
        target = float(g.target_amount)
        current = float(g.current_amount)
        pct = round((current / target * 100.0), 1) if target > 0 else 0.0
        res.append(SavingsGoalOut(
            id=g.id,
            user_id=g.user_id,
            title=g.title,
            target_amount=target,
            current_amount=current,
            progress_percentage=pct,
            target_date=str(g.target_date) if g.target_date else None,
        ))
    return res


@router.post("/goals", response_model=SavingsGoalOut)
def create_goal(
    goal_in: SavingsGoalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target = Decimal(str(abs(goal_in.target_amount))).quantize(Decimal("0.01"))
    current = Decimal(str(abs(goal_in.current_amount or 0.0))).quantize(Decimal("0.01"))
    g = SavingsGoal(
        user_id=current_user.id,
        title=goal_in.title,
        target_amount=target,
        current_amount=current,
        created_at=datetime.utcnow(),
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    pct = round((float(current) / float(target) * 100.0), 1) if float(target) > 0 else 0.0
    return SavingsGoalOut(
        id=g.id,
        user_id=g.user_id,
        title=g.title,
        target_amount=float(g.target_amount),
        current_amount=float(g.current_amount),
        progress_percentage=pct,
        target_date=None,
    )


# --- Long-Term Memory ---
@router.get("/memories", response_model=List[MemoryOut])
def get_memories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    mems = db.query(UserMemory).filter(
        UserMemory.user_id == current_user.id
    ).order_by(desc(UserMemory.updated_at)).all()
    return [MemoryOut.from_orm(m) for m in mems]


@router.post("/memories", response_model=MemoryOut)
def create_memory(
    mem_in: MemoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    mem = UserMemory(
        user_id=current_user.id,
        memory_type=mem_in.memory_type,
        content=mem_in.content.strip(),
        source=mem_in.source or "user",
        created_at=datetime.utcnow(),
    )
    db.add(mem)
    db.commit()
    db.refresh(mem)
    return MemoryOut.from_orm(mem)


@router.delete("/memories/{memory_id}")
def delete_memory(
    memory_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    mem = db.query(UserMemory).filter(UserMemory.id == memory_id, UserMemory.user_id == current_user.id).first()
    if not mem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    db.delete(mem)
    db.commit()
    return {"status": "success", "message": f"Memory {memory_id} deleted"}


@router.delete("/memories")
def clear_memories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deleted = db.query(UserMemory).filter(UserMemory.user_id == current_user.id).delete()
    db.commit()
    return {"status": "success", "message": f"Cleared {deleted} memories"}


from app.memory.checkpointer import get_graph_checkpointer, get_scoped_thread_id
from app.agents.confirmation import get_pending_proposal_for_thread, clear_pending_proposal_for_thread
from langchain_core.messages import HumanMessage, AIMessage

# --- Agent Query & Human-in-the-Loop Confirmation ---
@router.post("/agent/query", response_model=AgentResponse)
async def query_agent_route(
    request: QueryRequest,
    current_user: User = Depends(get_current_user),
):
    res = await run_finpilot_agent(
        query=request.query,
        thread_id=request.thread_id,
        user_id=current_user.id,
        user_currency=current_user.preferred_currency,
    )
    return AgentResponse(**res)


@router.get("/agent/history", response_model=AgentHistoryResponse)
def get_agent_history_route(
    thread_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    scoped_tid = get_scoped_thread_id(current_user.id, thread_id)
    cp = get_graph_checkpointer()
    messages_out = []
    pending_conf = None

    if cp:
        try:
            cfg = {"configurable": {"thread_id": scoped_tid}}
            cp_data = cp.get(cfg)
            if cp_data and "channel_values" in cp_data:
                cvals = cp_data["channel_values"]
                raw_msgs = cvals.get("messages", [])
                pending_conf = cvals.get("pending_action")
                
                for idx, m in enumerate(raw_msgs):
                    sender = "user" if isinstance(m, HumanMessage) else "assistant"
                    text = m.content if isinstance(m.content, str) else str(m.content)
                    messages_out.append(MessageHistoryItem(
                        id=f"msg_{idx}_{abs(hash(text)) % 1000000}",
                        sender=sender,
                        text=text,
                        timestamp=datetime.now().strftime("%I:%M %p"),
                    ))
        except Exception as e:
            pass

    # Fallback sync with thread proposal cache
    if not pending_conf:
        pending_conf = get_pending_proposal_for_thread(current_user.id, scoped_tid)

    return AgentHistoryResponse(
        thread_id=scoped_tid,
        messages=messages_out,
        pending_confirmation=pending_conf,
    )


@router.delete("/agent/history")
def clear_agent_history_route(
    thread_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    scoped_tid = get_scoped_thread_id(current_user.id, thread_id)
    clear_pending_proposal_for_thread(current_user.id, scoped_tid)
    cp = get_graph_checkpointer()
    if cp and hasattr(cp, "put"):
        try:
            cfg = {"configurable": {"thread_id": scoped_tid}}
            from langgraph.checkpoint.base import empty_checkpoint
            empty_cp = empty_checkpoint()
            empty_cp["channel_values"] = {"messages": [], "pending_action": None}
            cp.put(cfg, empty_cp, {"source": "reset"}, {})
        except Exception:
            pass
    return {"status": "success", "message": f"Conversation history cleared for {scoped_tid}"}


@router.post("/agent/confirm", response_model=ConfirmationActionResponse)
async def confirm_action_route(
    request: ConfirmationActionRequest,
    current_user: User = Depends(get_current_user),
):
    result = execute_confirmed_action(
        user_id=current_user.id,
        action_token=request.action_token,
        confirmed=request.confirmed,
    )
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error", "Failed to execute confirmation proposal.")
        )
    return ConfirmationActionResponse(
        success=True,
        status=result.get("status", "completed"),
        message=result.get("message", "Action executed successfully"),
        details=result.get("details"),
    )


# --- Voice Endpoints (STT & TTS) ---
@router.post("/voice/transcribe", response_model=SpeechToTextResponse)
async def voice_transcribe(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    contents = await file.read()
    transcript = await transcribe_audio_groq(contents, filename=file.filename or "audio.wav")
    return SpeechToTextResponse(transcript=transcript)


@router.post("/voice/synthesize")
async def voice_synthesize(
    text: str = Query(..., min_length=1),
    current_user: User = Depends(get_current_user),
):
    audio_bytes = await synthesize_speech(text)
    if not audio_bytes:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return Response(content=audio_bytes, media_type="audio/mpeg")
