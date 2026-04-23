from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LearningNodeStateOut(BaseModel):
    id: int
    user_id: int
    path_id: int
    node_id: int
    state: str
    progress_percent: int
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LearningNodeOut(BaseModel):
    id: int
    path_id: int
    node_code: str
    parent_node_id: int | None
    title: str
    node_type: str
    description: str | None
    est_minutes: int | None
    sort_no: int
    unlock_rule_json: dict[str, Any] | None
    content_json: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    user_state: LearningNodeStateOut | None = None

    model_config = ConfigDict(from_attributes=True)


class LearningPathOut(BaseModel):
    id: int
    user_id: int
    conversation_id: int
    source_task_id: int | None
    source_message_id: int | None
    version_no: int
    title: str
    goal: str | None
    summary_json: dict[str, Any] | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LearningPathDetailData(BaseModel):
    path: LearningPathOut
    nodes: list[LearningNodeOut]


class LearningNodeStateUpdateIn(BaseModel):
    state: str = Field(pattern="^(locked|available|in_progress|done)$")
    progress_percent: int | None = Field(default=None, ge=0, le=100)
    request_id: str | None = Field(default=None, max_length=64)


class LearningCheckinCreateIn(BaseModel):
    node_id: int | None = Field(default=None, ge=1)
    checkin_date: date | None = None
    spent_minutes: int = Field(default=0, ge=0, le=1440)
    note: str | None = Field(default=None, max_length=5000)
    evidence_json: dict[str, Any] | None = None
    request_id: str | None = Field(default=None, max_length=64)


class LearningCheckinOut(BaseModel):
    id: int
    user_id: int
    path_id: int
    node_id: int | None
    checkin_date: date
    spent_minutes: int
    note: str | None
    evidence_json: dict[str, Any] | None
    request_id: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LearningProgressData(BaseModel):
    path_id: int
    total_nodes: int
    done_nodes: int
    in_progress_nodes: int
    available_nodes: int
    locked_nodes: int
    completion_percent: float
    checkins_total: int
    checkin_days: int
    last_checkin_date: date | None


class ConversationEventOut(BaseModel):
    id: int
    conversation_id: int
    user_id: int | None
    event_type: str
    entity_type: str
    entity_id: int | None
    payload_json: dict[str, Any] | None
    request_id: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationEventListData(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ConversationEventOut]

