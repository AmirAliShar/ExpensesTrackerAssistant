from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import Conversation, ConversationMessage
from app.memory.checkpointer import get_scoped_thread_id


def ensure_conversation(db: Session, user_id: int, thread_id: str, title: Optional[str] = None) -> Conversation:
    scoped_thread_id = get_scoped_thread_id(user_id, thread_id)
    conversation = db.query(Conversation).filter(
        Conversation.user_id == user_id,
        Conversation.thread_id == scoped_thread_id,
    ).first()
    if conversation:
        conversation.updated_at = datetime.utcnow()
        db.commit()
        return conversation
    conversation = Conversation(
        user_id=user_id,
        thread_id=scoped_thread_id,
        title=(title or "New conversation").strip()[:255],
        archived=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def append_turn(
    db: Session,
    user_id: int,
    thread_id: str,
    user_text: str,
    assistant_text: str,
    metadata: Optional[Dict] = None,
) -> None:
    conversation = ensure_conversation(db, user_id, thread_id)
    if conversation.title == "New conversation" and user_text.strip():
        conversation.title = user_text.strip()[:60]
    db.add_all([
        ConversationMessage(
            conversation_id=conversation.id,
            role="user",
            content=user_text,
            message_metadata=None,
            created_at=datetime.utcnow(),
        ),
        ConversationMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=assistant_text,
            message_metadata=metadata,
            created_at=datetime.utcnow(),
        ),
    ])
    conversation.updated_at = datetime.utcnow()
    db.commit()


def list_conversations(db: Session, user_id: int, search: Optional[str] = None, include_archived: bool = False) -> List[Conversation]:
    query = db.query(Conversation).filter(Conversation.user_id == user_id)
    if not include_archived:
        query = query.filter(Conversation.archived.is_(False))
    if search:
        query = query.filter(Conversation.title.ilike(f"%{search.strip()}%"))
    return query.order_by(Conversation.updated_at.desc()).all()


def get_conversation(db: Session, user_id: int, thread_id: str) -> Optional[Conversation]:
    scoped = get_scoped_thread_id(user_id, thread_id)
    return db.query(Conversation).filter(
        Conversation.user_id == user_id,
        Conversation.thread_id == scoped,
    ).first()
