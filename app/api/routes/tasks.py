from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.serializers import serialize_single_message
from app.core.database import get_db
from app.core.response import ok
from app.models import (
    Conversation,
    GenerationTask,
    GenerationTaskStatus,
    Message,
    MessageRole,
    MessageType,
    User,
)
from app.schemas.task import GenerationTaskListData, GenerationTaskOut

router = APIRouter(prefix="/tasks", tags=["Tasks"])


def _get_owned_task(task_id: int, current_user: User, db: Session) -> GenerationTask:
    task = db.get(GenerationTask, task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    conversation = db.get(Conversation, task.conversation_id)
    if conversation is None or conversation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    return task


def _resolve_success_answer(task: GenerationTask, db: Session) -> Message | None:
    if task.status != GenerationTaskStatus.success:
        return None

    candidate_ids: list[int] = []
    if task.answer_message_id is not None:
        candidate_ids.append(task.answer_message_id)
    if (
        task.replace_answer_message_id is not None
        and task.replace_answer_message_id not in candidate_ids
    ):
        candidate_ids.append(task.replace_answer_message_id)

    for candidate_id in candidate_ids:
        candidate = db.get(Message, candidate_id)
        if (
            candidate is not None
            and candidate.conversation_id == task.conversation_id
            and candidate.role == MessageRole.assistant
            and candidate.message_type == MessageType.answer
        ):
            return candidate

    if task.question_message_id is None:
        return None

    return db.scalar(
        select(Message)
        .where(
            Message.conversation_id == task.conversation_id,
            Message.parent_message_id == task.question_message_id,
            Message.role == MessageRole.assistant,
            Message.message_type == MessageType.answer,
        )
        .order_by(Message.id.desc())
        .limit(1)
    )


@router.get("/{task_id}")
def get_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    task = _get_owned_task(task_id, current_user, db)
    return ok(GenerationTaskOut.model_validate(task).model_dump())


@router.get("/{task_id}/result")
def get_task_result(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    task = _get_owned_task(task_id, current_user, db)
    answer_message = _resolve_success_answer(task, db)

    data = {
        "task": GenerationTaskOut.model_validate(task).model_dump(),
        "answer_ready": answer_message is not None,
        "answer_message": serialize_single_message(db, answer_message) if answer_message else None,
    }
    return ok(data)


@router.get("")
def list_tasks(
    conversation_id: int | None = Query(default=None, ge=1),
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    allowed_status = {"pending", "running", "success", "failed"}
    if status_filter is not None and status_filter not in allowed_status:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid status filter",
        )

    base_stmt = (
        select(GenerationTask)
        .join(Conversation, Conversation.id == GenerationTask.conversation_id)
        .where(Conversation.user_id == current_user.id)
    )

    if conversation_id is not None:
        base_stmt = base_stmt.where(GenerationTask.conversation_id == conversation_id)
    if status_filter is not None:
        base_stmt = base_stmt.where(GenerationTask.status == status_filter)

    total = db.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0
    rows = db.scalars(
        base_stmt
        .order_by(GenerationTask.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    data = GenerationTaskListData(
        total=total,
        page=page,
        page_size=page_size,
        items=[GenerationTaskOut.model_validate(row) for row in rows],
    )
    return ok(data.model_dump())
