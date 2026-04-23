from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.api.internal_auth import verify_internal_token
from app.api.serializers import serialize_single_message
from app.core.database import get_db
from app.core.response import ok
from app.models import (
    ConversationEvent,
    Conversation,
    GenerationTask,
    GenerationTaskStatus,
    LearningNode,
    LearningNodeState,
    LearningNodeStateValue,
    LearningNodeType,
    LearningPath,
    LearningPathStatus,
    Message,
    MessageAsset,
    MessageAssetType,
    MessageRole,
    MessageType,
)
from app.schemas.message import ModelAnswerCallbackIn
from app.schemas.task import GenerationTaskOut, ModelFailureCallbackIn

router = APIRouter(prefix="/callbacks", tags=["Callbacks"])


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _extract_learning_path(meta_json: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(meta_json, dict):
        return None
    learning_path = meta_json.get("learning_path")
    return learning_path if isinstance(learning_path, dict) else None


def _safe_int(value: Any, default: int | None = None) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _store_learning_path_from_answer(
    db: Session,
    conversation: Conversation,
    task: GenerationTask | None,
    answer_message: Message,
    meta_json: dict[str, Any] | None,
) -> None:
    learning_path_data = _extract_learning_path(meta_json)
    if learning_path_data is None:
        return

    db.execute(
        update(LearningPath)
        .where(
            LearningPath.user_id == conversation.user_id,
            LearningPath.conversation_id == conversation.id,
            LearningPath.status == LearningPathStatus.active,
        )
        .values(status=LearningPathStatus.archived)
    )

    current_max_version = db.scalar(
        select(func.max(LearningPath.version_no)).where(
            LearningPath.user_id == conversation.user_id,
            LearningPath.conversation_id == conversation.id,
        )
    ) or 0

    path = LearningPath(
        user_id=conversation.user_id,
        conversation_id=conversation.id,
        source_task_id=task.id if task else None,
        source_message_id=answer_message.id,
        version_no=current_max_version + 1,
        title=(_string_or_none(learning_path_data.get("title")) or "Learning Path")[:255],
        goal=_string_or_none(learning_path_data.get("goal")),
        summary_json=(
            learning_path_data.get("summary_json")
            if isinstance(learning_path_data.get("summary_json"), dict)
            else None
        ),
        status=LearningPathStatus.active,
    )
    db.add(path)
    db.flush()

    raw_nodes = learning_path_data.get("nodes")
    node_rows = raw_nodes if isinstance(raw_nodes, list) else []
    created_nodes: list[LearningNode] = []
    node_id_by_code: dict[str, int] = {}
    pending_parent_refs: list[tuple[LearningNode, str]] = []
    used_codes: set[str] = set()
    allowed_types = {item.value for item in LearningNodeType}

    for idx, row in enumerate(node_rows, start=1):
        if not isinstance(row, dict):
            continue

        base_code = (_string_or_none(row.get("node_code")) or f"N{idx}")[:64]
        node_code = base_code
        serial_no = 2
        while node_code in used_codes:
            suffix = f"_{serial_no}"
            node_code = f"{base_code[: max(1, 64 - len(suffix))]}{suffix}"
            serial_no += 1
        used_codes.add(node_code)

        node_type_raw = (_string_or_none(row.get("node_type")) or "lesson").lower()
        node_type = node_type_raw if node_type_raw in allowed_types else LearningNodeType.other.value
        sort_no = _safe_int(row.get("sort_no"), idx) or idx
        est_minutes = _safe_int(row.get("est_minutes"))
        if est_minutes is not None and est_minutes < 0:
            est_minutes = None

        node = LearningNode(
            path_id=path.id,
            node_code=node_code,
            title=(_string_or_none(row.get("title")) or f"Step {idx}")[:255],
            node_type=LearningNodeType(node_type),
            description=_string_or_none(row.get("description")),
            est_minutes=est_minutes,
            sort_no=sort_no,
            unlock_rule_json=row.get("unlock_rule_json")
            if isinstance(row.get("unlock_rule_json"), dict)
            else None,
            content_json=row.get("content_json")
            if isinstance(row.get("content_json"), dict)
            else None,
        )
        db.add(node)
        db.flush()

        created_nodes.append(node)
        node_id_by_code[node_code] = node.id
        parent_code = _string_or_none(row.get("parent_node_code"))
        if parent_code:
            pending_parent_refs.append((node, parent_code[:64]))

    for node, parent_code in pending_parent_refs:
        parent_id = node_id_by_code.get(parent_code)
        if parent_id is not None and parent_id != node.id:
            node.parent_node_id = parent_id

    sorted_nodes = sorted(created_nodes, key=lambda item: (item.sort_no, item.id))
    for index, node in enumerate(sorted_nodes):
        node_state = (
            LearningNodeStateValue.available if index == 0 else LearningNodeStateValue.locked
        )
        db.add(
            LearningNodeState(
                user_id=conversation.user_id,
                path_id=path.id,
                node_id=node.id,
                state=node_state,
                progress_percent=0,
            )
        )

    db.add(
        ConversationEvent(
            conversation_id=conversation.id,
            user_id=None,
            event_type="learning_path_generated",
            entity_type="learning_path",
            entity_id=path.id,
            payload_json={
                "path_id": path.id,
                "version_no": path.version_no,
                "title": path.title,
                "node_count": len(created_nodes),
                "source_task_id": task.id if task else None,
                "source_message_id": answer_message.id,
            },
            request_id=None,
        )
    )


@router.post("/model-answer")
def receive_model_answer(
    payload: ModelAnswerCallbackIn,
    _token_guard: None = Depends(verify_internal_token),
    db: Session = Depends(get_db),
) -> dict:
    if (
        payload.generation_task_id is None
        and payload.question_message_id is None
        and payload.backend_task_id is None
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="generation_task_id or question_message_id or backend_task_id is required",
        )

    conversation = db.get(Conversation, payload.conversation_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    task: GenerationTask | None = None
    if payload.generation_task_id is not None:
        task = db.get(GenerationTask, payload.generation_task_id)
        if task is None or task.conversation_id != payload.conversation_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Generation task not found",
            )
    elif payload.backend_task_id:
        task = db.scalar(
            select(GenerationTask).where(GenerationTask.backend_task_id == payload.backend_task_id)
        )
        if task is not None and task.conversation_id != payload.conversation_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="backend_task_id does not match conversation",
            )

    question_message_id = (
        task.question_message_id if task and task.question_message_id else payload.question_message_id
    )
    if question_message_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="question_message_id is missing",
        )

    question_message = db.get(Message, question_message_id)
    if question_message is None or question_message.conversation_id != payload.conversation_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question message not found",
        )
    if question_message.role != MessageRole.user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="question_message_id must reference a user message",
        )

    answer_request_id = payload.answer_request_id
    if not answer_request_id:
        if task is not None:
            answer_request_id = f"answer-task-{task.id}"
        else:
            answer_request_id = f"answer-question-{question_message_id}"

    existed = db.scalar(
        select(Message).where(Message.request_id == answer_request_id)
    )
    if existed is not None:
        if existed.conversation_id != payload.conversation_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="answer_request_id already used in another conversation",
            )
        return ok(serialize_single_message(db, existed), "Duplicate callback ignored")

    answer_text = payload.answer_text.strip()
    if not answer_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="answer_text cannot be blank",
        )

    answer_message: Message
    if task is not None and task.replace_answer_message_id is not None:
        answer_message = db.get(Message, task.replace_answer_message_id)
        if (
            answer_message is None
            or answer_message.conversation_id != payload.conversation_id
            or answer_message.role != MessageRole.assistant
            or answer_message.message_type != MessageType.answer
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Target answer message for overwrite not found",
            )

        answer_message.content_text = answer_text
        answer_message.request_id = answer_request_id
        answer_message.parent_message_id = question_message_id
        answer_message.meta_json = payload.meta_json
        db.execute(delete(MessageAsset).where(MessageAsset.message_id == answer_message.id))
    else:
        answer_message = Message(
            conversation_id=payload.conversation_id,
            role=MessageRole.assistant,
            message_type=MessageType.answer,
            content_text=answer_text,
            request_id=answer_request_id,
            parent_message_id=question_message_id,
            meta_json=payload.meta_json,
        )
        db.add(answer_message)
        db.flush()

    for asset in payload.assets:
        db.add(
            MessageAsset(
                message_id=answer_message.id,
                asset_type=MessageAssetType(asset.asset_type),
                asset_url=asset.asset_url,
                mime_type=asset.mime_type,
                title=asset.title,
                sort_no=asset.sort_no,
                meta_json=asset.meta_json,
            )
        )

    now = datetime.utcnow()
    conversation.last_message_at = now

    if task is None:
        task = GenerationTask(
            conversation_id=payload.conversation_id,
            question_message_id=question_message_id,
            answer_message_id=answer_message.id,
            status=GenerationTaskStatus.success,
            backend_task_id=payload.backend_task_id,
            model_name=payload.model_name,
            finished_at=now,
            lease_expires_at=None,
        )
        db.add(task)
    else:
        task.status = GenerationTaskStatus.success
        task.answer_message_id = answer_message.id
        if payload.backend_task_id:
            task.backend_task_id = payload.backend_task_id
        if payload.model_name:
            task.model_name = payload.model_name
        task.error_message = None
        task.finished_at = now
        task.lease_expires_at = None

    _store_learning_path_from_answer(
        db=db,
        conversation=conversation,
        task=task,
        answer_message=answer_message,
        meta_json=payload.meta_json,
    )

    db.commit()
    db.refresh(answer_message)

    return ok(serialize_single_message(db, answer_message), "Answer stored")


@router.post("/model-failure")
def receive_model_failure(
    payload: ModelFailureCallbackIn,
    _token_guard: None = Depends(verify_internal_token),
    db: Session = Depends(get_db),
) -> dict:
    if payload.generation_task_id is None and payload.backend_task_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="generation_task_id or backend_task_id is required",
        )

    conversation = db.get(Conversation, payload.conversation_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    task: GenerationTask | None = None
    if payload.generation_task_id is not None:
        task = db.get(GenerationTask, payload.generation_task_id)
    elif payload.backend_task_id is not None:
        task = db.scalar(
            select(GenerationTask).where(GenerationTask.backend_task_id == payload.backend_task_id)
        )

    if task is None or task.conversation_id != payload.conversation_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generation task not found",
        )

    task.status = GenerationTaskStatus.failed
    if payload.backend_task_id:
        task.backend_task_id = payload.backend_task_id
    if payload.model_name:
        task.model_name = payload.model_name
    task.error_message = payload.error_message.strip()
    task.finished_at = datetime.utcnow()
    task.lease_expires_at = None

    db.commit()
    db.refresh(task)
    return ok(GenerationTaskOut.model_validate(task).model_dump(), "Failure stored")
