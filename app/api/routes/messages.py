from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.serializers import serialize_single_message
from app.core.database import get_db
from app.core.response import ok
from app.models import (
    Conversation,
    ConversationStatus,
    Feedback,
    FeedbackRating,
    GenerationTask,
    GenerationTaskStatus,
    Message,
    MessageRole,
    MessageType,
    User,
)
from app.schemas.message import QuestionCreate
from app.schemas.task import MessageFeedbackCreate, MessageFeedbackOut

router = APIRouter(prefix="/messages", tags=["Messages"])


@router.post("/question")
def submit_question(
    payload: QuestionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    conversation = db.get(Conversation, payload.conversation_id)
    if conversation is None or conversation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    if conversation.current_status != ConversationStatus.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Conversation is not active",
        )

    content = payload.content_text.strip()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Question content cannot be blank",
        )

    if payload.request_id:
        existed = db.scalar(
            select(Message).where(Message.request_id == payload.request_id)
        )
        if existed is not None:
            if existed.conversation_id != conversation.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="request_id already used in another conversation",
                )
            existed_task = db.scalar(
                select(GenerationTask)
                .where(GenerationTask.question_message_id == existed.id)
                .order_by(GenerationTask.id.desc())
            )
            data = serialize_single_message(db, existed)
            data["generation_task_id"] = existed_task.id if existed_task else None
            return ok(data, "Duplicate request ignored")

    message = Message(
        conversation_id=conversation.id,
        role=MessageRole.user,
        message_type=MessageType.question,
        content_text=content,
        request_id=payload.request_id,
    )
    db.add(message)
    db.flush()

    task = GenerationTask(
        conversation_id=conversation.id,
        question_message_id=message.id,
        status=GenerationTaskStatus.pending,
        frontend_request_id=payload.request_id,
    )
    db.add(task)
    conversation.last_message_at = datetime.utcnow()

    db.commit()
    db.refresh(message)
    db.refresh(task)

    data = serialize_single_message(db, message)
    data["generation_task_id"] = task.id
    return ok(data, "Question accepted")


@router.post("/{message_id}/feedback")
def submit_feedback(
    message_id: int,
    payload: MessageFeedbackCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    message = db.get(Message, message_id)
    if message is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )

    conversation = db.get(Conversation, message.conversation_id)
    if conversation is None or conversation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )

    if message.role != MessageRole.assistant or message.message_type != MessageType.answer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Feedback is only allowed for assistant answer messages",
        )

    if payload.request_id:
        existed = db.scalar(select(Feedback).where(Feedback.request_id == payload.request_id))
        if existed is not None:
            if existed.message_id != message_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="request_id already used for another feedback",
                )
            data = MessageFeedbackOut.model_validate(existed).model_dump()
            existed_regen_task_id = db.scalar(
                select(GenerationTask.id)
                .where(GenerationTask.feedback_id == existed.id)
                .order_by(GenerationTask.id.desc())
            )
            data["regenerate_task_id"] = existed_regen_task_id
            return ok(data, "Duplicate feedback ignored")

    feedback = Feedback(
        conversation_id=conversation.id,
        message_id=message.id,
        user_id=current_user.id,
        rating=FeedbackRating(payload.rating),
        reason=payload.reason,
        detail=payload.detail,
        request_id=payload.request_id,
    )
    db.add(feedback)
    db.flush()

    regenerate_task_id: int | None = None
    if payload.regenerate:
        if message.parent_message_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot regenerate because parent question is missing",
            )

        regen_task = GenerationTask(
            conversation_id=conversation.id,
            question_message_id=message.parent_message_id,
            replace_answer_message_id=message.id,
            feedback_id=feedback.id,
            status=GenerationTaskStatus.pending,
            frontend_request_id=payload.request_id,
        )
        db.add(regen_task)
        db.flush()
        regenerate_task_id = regen_task.id
        conversation.last_message_at = datetime.utcnow()

    db.commit()
    db.refresh(feedback)

    data = MessageFeedbackOut.model_validate(feedback).model_dump()
    data["regenerate_task_id"] = regenerate_task_id
    return ok(data, "Feedback accepted")
