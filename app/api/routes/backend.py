from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.internal_auth import verify_internal_token
from app.core.config import settings
from app.core.database import get_db
from app.core.response import ok
from app.models import (
    Feedback,
    GenerationTask,
    GenerationTaskStatus,
    Message,
    MessageRole,
    MessageType,
)
from app.schemas.task import (
    BackendTaskClaimData,
    BackendTaskClaimRequest,
    BackendTaskHeartbeatRequest,
    GenerationTaskOut,
)

router = APIRouter(prefix="/backend", tags=["Backend"])


def _generate_backend_task_id() -> str:
    return f"job-{uuid4().hex[:24]}"


def _resolve_lease_seconds(requested: int | None) -> int:
    if requested is not None:
        return max(30, min(3600, requested))
    return max(30, min(3600, settings.backend_task_lease_seconds))


def _find_claimable_task(
    db: Session,
    conversation_id: int | None,
    now: datetime,
) -> tuple[GenerationTask | None, bool]:
    pending_stmt = (
        select(GenerationTask)
        .where(GenerationTask.status == GenerationTaskStatus.pending)
        .order_by(GenerationTask.id.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if conversation_id is not None:
        pending_stmt = pending_stmt.where(GenerationTask.conversation_id == conversation_id)

    task = db.scalar(pending_stmt)
    if task is not None:
        return task, False

    reclaim_stmt = (
        select(GenerationTask)
        .where(
            GenerationTask.status == GenerationTaskStatus.running,
            GenerationTask.lease_expires_at.is_not(None),
            GenerationTask.lease_expires_at < now,
        )
        .order_by(GenerationTask.lease_expires_at.asc(), GenerationTask.id.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if conversation_id is not None:
        reclaim_stmt = reclaim_stmt.where(GenerationTask.conversation_id == conversation_id)

    task = db.scalar(reclaim_stmt)
    if task is not None:
        return task, True
    return None, False


@router.post("/tasks/claim")
def claim_pending_task(
    payload: BackendTaskClaimRequest,
    _token_guard: None = Depends(verify_internal_token),
    db: Session = Depends(get_db),
) -> dict:
    now = datetime.utcnow()
    lease_seconds = _resolve_lease_seconds(payload.lease_seconds)
    lease_expires_at = now + timedelta(seconds=lease_seconds)
    claimed: BackendTaskClaimData | None = None
    reclaimed_stale = False

    with db.begin():
        for _ in range(30):
            task, reclaimed = _find_claimable_task(db, payload.conversation_id, now)
            if task is None:
                break

            question_message = (
                db.get(Message, task.question_message_id) if task.question_message_id else None
            )
            if (
                question_message is None
                or question_message.role != MessageRole.user
                or question_message.message_type != MessageType.question
            ):
                task.status = GenerationTaskStatus.failed
                task.error_message = "question message missing or invalid"
                task.finished_at = datetime.utcnow()
                task.lease_expires_at = None
                continue

            backend_task_id = payload.backend_task_id or _generate_backend_task_id()
            existed = db.scalar(
                select(GenerationTask).where(GenerationTask.backend_task_id == backend_task_id)
            )
            if existed is not None and existed.id != task.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="backend_task_id already exists",
                )

            task.status = GenerationTaskStatus.running
            task.backend_task_id = backend_task_id
            task.worker_id = payload.worker_id
            task.claimed_at = now
            task.lease_expires_at = lease_expires_at
            task.dispatch_attempts = (task.dispatch_attempts or 0) + 1
            task.finished_at = None
            if payload.model_name:
                task.model_name = payload.model_name
            task.error_message = None

            feedback = db.get(Feedback, task.feedback_id) if task.feedback_id else None

            claimed = BackendTaskClaimData(
                task_id=task.id,
                backend_task_id=backend_task_id,
                conversation_id=task.conversation_id,
                question_message_id=question_message.id,
                replace_answer_message_id=task.replace_answer_message_id,
                feedback_id=task.feedback_id,
                feedback_rating=feedback.rating.value if feedback else None,
                feedback_reason=feedback.reason if feedback else None,
                feedback_detail=feedback.detail if feedback else None,
                frontend_request_id=task.frontend_request_id,
                question_text=question_message.content_text,
                question_request_id=question_message.request_id,
                question_meta_json=question_message.meta_json,
                worker_id=payload.worker_id,
                model_name=task.model_name,
                claimed_at=task.claimed_at,
                lease_expires_at=task.lease_expires_at,
                dispatch_attempts=task.dispatch_attempts,
            )
            reclaimed_stale = reclaimed
            break

    if claimed is None:
        return ok(None, "No pending task")
    if reclaimed_stale:
        return ok(claimed.model_dump(), "Task re-claimed from expired lease")
    return ok(claimed.model_dump(), "Task claimed")


@router.post("/tasks/{task_id}/heartbeat")
def heartbeat_task(
    task_id: int,
    payload: BackendTaskHeartbeatRequest,
    _token_guard: None = Depends(verify_internal_token),
    db: Session = Depends(get_db),
) -> dict:
    lease_seconds = _resolve_lease_seconds(payload.lease_seconds)
    now = datetime.utcnow()
    new_expire = now + timedelta(seconds=lease_seconds)

    task = db.get(GenerationTask, task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    if task.status != GenerationTaskStatus.running:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Task is not running",
        )
    if payload.worker_id and task.worker_id and payload.worker_id != task.worker_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="worker_id does not match task owner",
        )

    task.lease_expires_at = new_expire
    db.commit()
    db.refresh(task)
    return ok(GenerationTaskOut.model_validate(task).model_dump(), "Lease extended")
