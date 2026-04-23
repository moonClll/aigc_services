from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.response import ok
from app.models import (
    Conversation,
    ConversationEvent,
    LearningCheckin,
    LearningNode,
    LearningNodeState,
    LearningNodeStateValue,
    LearningPath,
    LearningPathStatus,
    User,
)
from app.schemas.learning import (
    ConversationEventListData,
    ConversationEventOut,
    LearningCheckinCreateIn,
    LearningCheckinOut,
    LearningNodeOut,
    LearningNodeStateOut,
    LearningNodeStateUpdateIn,
    LearningPathDetailData,
    LearningPathOut,
    LearningProgressData,
)

router = APIRouter(prefix="/learning-paths", tags=["Learning"])


def _get_owned_conversation(conversation_id: int, current_user: User, db: Session) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    return conversation


def _get_owned_path(path_id: int, current_user: User, db: Session) -> LearningPath:
    path = db.get(LearningPath, path_id)
    if path is None or path.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Learning path not found",
        )
    return path


def _get_or_create_node_state(
    db: Session,
    path: LearningPath,
    node: LearningNode,
    user_id: int,
) -> LearningNodeState:
    state = db.scalar(
        select(LearningNodeState).where(
            LearningNodeState.user_id == user_id,
            LearningNodeState.path_id == path.id,
            LearningNodeState.node_id == node.id,
        )
    )
    if state is not None:
        return state

    default_state = (
        LearningNodeStateValue.available if node.sort_no <= 1 else LearningNodeStateValue.locked
    )
    state = LearningNodeState(
        user_id=user_id,
        path_id=path.id,
        node_id=node.id,
        state=default_state,
        progress_percent=0,
    )
    db.add(state)
    db.flush()
    return state


def _build_path_detail(path: LearningPath, current_user: User, db: Session) -> dict:
    nodes = db.scalars(
        select(LearningNode)
        .where(LearningNode.path_id == path.id)
        .order_by(LearningNode.sort_no.asc(), LearningNode.id.asc())
    ).all()
    state_rows = db.scalars(
        select(LearningNodeState).where(
            LearningNodeState.path_id == path.id,
            LearningNodeState.user_id == current_user.id,
        )
    ).all()
    state_map = {row.node_id: row for row in state_rows}

    items: list[LearningNodeOut] = []
    for node in nodes:
        node_data = LearningNodeOut.model_validate(node).model_dump()
        state = state_map.get(node.id)
        node_data["user_state"] = (
            LearningNodeStateOut.model_validate(state).model_dump() if state else None
        )
        items.append(LearningNodeOut.model_validate(node_data))

    data = LearningPathDetailData(
        path=LearningPathOut.model_validate(path),
        nodes=items,
    )
    return data.model_dump()


@router.get("/conversations/{conversation_id}/current")
def get_current_learning_path(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _get_owned_conversation(conversation_id, current_user, db)

    path = db.scalar(
        select(LearningPath)
        .where(
            LearningPath.user_id == current_user.id,
            LearningPath.conversation_id == conversation_id,
            LearningPath.status == LearningPathStatus.active,
        )
        .order_by(LearningPath.version_no.desc(), LearningPath.id.desc())
        .limit(1)
    )
    if path is None:
        path = db.scalar(
            select(LearningPath)
            .where(
                LearningPath.user_id == current_user.id,
                LearningPath.conversation_id == conversation_id,
            )
            .order_by(LearningPath.version_no.desc(), LearningPath.id.desc())
            .limit(1)
        )
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Learning path not found",
        )

    return ok(_build_path_detail(path, current_user, db))


@router.get("/{path_id}")
def get_learning_path(
    path_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    path = _get_owned_path(path_id, current_user, db)
    return ok(_build_path_detail(path, current_user, db))


@router.patch("/{path_id}/nodes/{node_id}/state")
def update_learning_node_state(
    path_id: int,
    node_id: int,
    payload: LearningNodeStateUpdateIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    path = _get_owned_path(path_id, current_user, db)
    node = db.get(LearningNode, node_id)
    if node is None or node.path_id != path.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Learning node not found",
        )

    if payload.request_id:
        existed_event = db.scalar(
            select(ConversationEvent).where(ConversationEvent.request_id == payload.request_id)
        )
        if existed_event is not None:
            if (
                existed_event.conversation_id != path.conversation_id
                or existed_event.event_type != "learning_node_state_updated"
                or existed_event.entity_type != "learning_node"
                or existed_event.entity_id != node.id
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="request_id already used in another update",
                )
            state = _get_or_create_node_state(db, path, node, current_user.id)
            return ok(
                LearningNodeStateOut.model_validate(state).model_dump(),
                "Duplicate update ignored",
            )

    state = _get_or_create_node_state(db, path, node, current_user.id)
    new_state = LearningNodeStateValue(payload.state)
    now = datetime.utcnow()

    state.state = new_state
    if new_state == LearningNodeStateValue.locked:
        state.progress_percent = payload.progress_percent or 0
        state.started_at = None
        state.completed_at = None
    elif new_state == LearningNodeStateValue.available:
        if payload.progress_percent is not None:
            state.progress_percent = payload.progress_percent
        state.completed_at = None
    elif new_state == LearningNodeStateValue.in_progress:
        if state.started_at is None:
            state.started_at = now
        if payload.progress_percent is not None:
            state.progress_percent = payload.progress_percent
        if state.progress_percent <= 0:
            state.progress_percent = 1
        state.completed_at = None
    else:
        state.progress_percent = 100
        if state.started_at is None:
            state.started_at = now
        if state.completed_at is None:
            state.completed_at = now

        next_node = db.scalar(
            select(LearningNode)
            .where(
                LearningNode.path_id == path.id,
                (
                    (LearningNode.sort_no > node.sort_no)
                    | (
                        (LearningNode.sort_no == node.sort_no)
                        & (LearningNode.id > node.id)
                    )
                ),
            )
            .order_by(LearningNode.sort_no.asc(), LearningNode.id.asc())
            .limit(1)
        )
        if next_node is not None:
            next_state = _get_or_create_node_state(db, path, next_node, current_user.id)
            if next_state.state == LearningNodeStateValue.locked:
                next_state.state = LearningNodeStateValue.available

    db.add(
        ConversationEvent(
            conversation_id=path.conversation_id,
            user_id=current_user.id,
            event_type="learning_node_state_updated",
            entity_type="learning_node",
            entity_id=node.id,
            payload_json={
                "path_id": path.id,
                "node_id": node.id,
                "state": state.state.value,
                "progress_percent": state.progress_percent,
            },
            request_id=payload.request_id,
        )
    )

    db.commit()
    db.refresh(state)
    return ok(LearningNodeStateOut.model_validate(state).model_dump(), "State updated")


@router.post("/{path_id}/checkins")
def create_learning_checkin(
    path_id: int,
    payload: LearningCheckinCreateIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    path = _get_owned_path(path_id, current_user, db)
    node: LearningNode | None = None

    if payload.node_id is not None:
        node = db.get(LearningNode, payload.node_id)
        if node is None or node.path_id != path.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Learning node not found",
            )

    if payload.request_id:
        existed_event = db.scalar(
            select(ConversationEvent).where(ConversationEvent.request_id == payload.request_id)
        )
        if existed_event is not None:
            if (
                existed_event.conversation_id != path.conversation_id
                or existed_event.event_type != "learning_checkin_created"
                or existed_event.entity_type != "learning_checkin"
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="request_id already used in another update",
                )
            existed_checkin = (
                db.get(LearningCheckin, existed_event.entity_id)
                if existed_event.entity_id is not None
                else None
            )
            if (
                existed_checkin is not None
                and existed_checkin.path_id == path.id
                and existed_checkin.user_id == current_user.id
            ):
                return ok(
                    LearningCheckinOut.model_validate(existed_checkin).model_dump(),
                    "Duplicate check-in ignored",
                )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="request_id already used in another check-in",
            )

    if payload.request_id:
        existed = db.scalar(
            select(LearningCheckin).where(LearningCheckin.request_id == payload.request_id)
        )
        if existed is not None:
            if existed.path_id != path.id or existed.user_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="request_id already used in another check-in",
                )
            return ok(
                LearningCheckinOut.model_validate(existed).model_dump(),
                "Duplicate check-in ignored",
            )

    now = datetime.utcnow()
    checkin = LearningCheckin(
        user_id=current_user.id,
        path_id=path.id,
        node_id=node.id if node else None,
        checkin_date=payload.checkin_date or date.today(),
        spent_minutes=payload.spent_minutes,
        note=payload.note,
        evidence_json=payload.evidence_json,
        request_id=payload.request_id,
    )
    db.add(checkin)
    db.flush()

    if node is not None:
        node_state = _get_or_create_node_state(db, path, node, current_user.id)
        if node_state.state in {LearningNodeStateValue.locked, LearningNodeStateValue.available}:
            node_state.state = LearningNodeStateValue.in_progress
        if node_state.started_at is None:
            node_state.started_at = now
        if node_state.progress_percent <= 0:
            node_state.progress_percent = 1

    db.add(
        ConversationEvent(
            conversation_id=path.conversation_id,
            user_id=current_user.id,
            event_type="learning_checkin_created",
            entity_type="learning_checkin",
            entity_id=checkin.id,
            payload_json={
                "path_id": path.id,
                "node_id": checkin.node_id,
                "checkin_date": str(checkin.checkin_date),
                "spent_minutes": checkin.spent_minutes,
            },
            request_id=payload.request_id,
        )
    )

    db.commit()
    db.refresh(checkin)
    return ok(LearningCheckinOut.model_validate(checkin).model_dump(), "Check-in created")


@router.get("/{path_id}/progress")
def get_learning_progress(
    path_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    path = _get_owned_path(path_id, current_user, db)

    total_nodes = db.scalar(
        select(func.count()).select_from(
            select(LearningNode.id)
            .where(LearningNode.path_id == path.id)
            .subquery()
        )
    ) or 0

    state_rows = db.execute(
        select(LearningNodeState.state, func.count())
        .where(
            LearningNodeState.path_id == path.id,
            LearningNodeState.user_id == current_user.id,
        )
        .group_by(LearningNodeState.state)
    ).all()
    state_count_map = {str(row[0].value if hasattr(row[0], "value") else row[0]): int(row[1]) for row in state_rows}

    done_nodes = state_count_map.get(LearningNodeStateValue.done.value, 0)
    in_progress_nodes = state_count_map.get(LearningNodeStateValue.in_progress.value, 0)
    available_nodes = state_count_map.get(LearningNodeStateValue.available.value, 0)
    explicit_locked = state_count_map.get(LearningNodeStateValue.locked.value, 0)
    tracked_nodes = done_nodes + in_progress_nodes + available_nodes + explicit_locked
    locked_nodes = explicit_locked + max(total_nodes - tracked_nodes, 0)

    checkins_total = db.scalar(
        select(func.count())
        .select_from(
            select(LearningCheckin.id)
            .where(
                LearningCheckin.user_id == current_user.id,
                LearningCheckin.path_id == path.id,
            )
            .subquery()
        )
    ) or 0
    checkin_days = db.scalar(
        select(func.count(func.distinct(LearningCheckin.checkin_date))).where(
            LearningCheckin.user_id == current_user.id,
            LearningCheckin.path_id == path.id,
        )
    ) or 0
    last_checkin_date = db.scalar(
        select(func.max(LearningCheckin.checkin_date)).where(
            LearningCheckin.user_id == current_user.id,
            LearningCheckin.path_id == path.id,
        )
    )

    completion_percent = round((done_nodes * 100.0 / total_nodes), 2) if total_nodes > 0 else 0.0
    data = LearningProgressData(
        path_id=path.id,
        total_nodes=total_nodes,
        done_nodes=done_nodes,
        in_progress_nodes=in_progress_nodes,
        available_nodes=available_nodes,
        locked_nodes=locked_nodes,
        completion_percent=completion_percent,
        checkins_total=checkins_total,
        checkin_days=checkin_days,
        last_checkin_date=last_checkin_date,
    )
    return ok(data.model_dump())


@router.get("/conversations/{conversation_id}/events")
def list_conversation_events(
    conversation_id: int,
    event_type: str | None = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _get_owned_conversation(conversation_id, current_user, db)

    base_stmt = select(ConversationEvent).where(ConversationEvent.conversation_id == conversation_id)
    if event_type:
        base_stmt = base_stmt.where(ConversationEvent.event_type == event_type)

    total = db.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0
    rows = db.scalars(
        base_stmt
        .order_by(ConversationEvent.created_at.desc(), ConversationEvent.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    data = ConversationEventListData(
        total=total,
        page=page,
        page_size=page_size,
        items=[ConversationEventOut.model_validate(row) for row in rows],
    )
    return ok(data.model_dump())
