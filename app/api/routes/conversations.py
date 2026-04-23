from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.serializers import serialize_messages
from app.core.database import get_db
from app.core.response import ok
from app.models import Conversation, ConversationStatus, Message, User
from app.schemas.conversation import (
    ConversationCreate,
    ConversationListData,
    ConversationOut,
    ConversationTitleListData,
    ConversationTitleOut,
)
from app.schemas.message import MessageListData

router = APIRouter(prefix="/conversations", tags=["Conversations"])


@router.post("")
def create_conversation(
    payload: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    title = (payload.title or "").strip() or "New Conversation"
    conversation = Conversation(
        user_id=current_user.id,
        title=title,
        current_status=ConversationStatus.active,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return ok(ConversationOut.model_validate(conversation).model_dump(), "Conversation created")


@router.get("")
def list_conversations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    base_stmt = select(Conversation).where(Conversation.user_id == current_user.id)
    total = db.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0

    rows = db.scalars(
        base_stmt
        .order_by(Conversation.last_message_at.desc(), Conversation.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    data = ConversationListData(
        total=total,
        page=page,
        page_size=page_size,
        items=[ConversationOut.model_validate(row) for row in rows],
    )
    return ok(data.model_dump())


@router.get("/titles")
def list_conversation_titles(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.scalars(
        select(Conversation)
        .where(Conversation.user_id == current_user.id)
        .order_by(Conversation.last_message_at.desc(), Conversation.id.desc())
    ).all()

    data = ConversationTitleListData(
        total=len(rows),
        items=[ConversationTitleOut.model_validate(row) for row in rows],
    )
    return ok(data.model_dump())


@router.get("/{conversation_id}/messages")
def list_conversation_messages(
    conversation_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    base_stmt = select(Message).where(Message.conversation_id == conversation_id)
    total = db.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0

    rows = db.scalars(
        base_stmt
        .order_by(Message.created_at.asc(), Message.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    data = MessageListData(
        total=total,
        page=page,
        page_size=page_size,
        items=serialize_messages(db, rows),
    )
    return ok(data.model_dump())


@router.get("/{conversation_id}/messages/all")
def list_conversation_messages_all(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    rows = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    ).all()

    data = MessageListData(
        total=len(rows),
        page=1,
        page_size=len(rows) if rows else 0,
        items=serialize_messages(db, rows),
    )
    return ok(data.model_dump())
