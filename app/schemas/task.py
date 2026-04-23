from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GenerationTaskOut(BaseModel):
    id: int
    conversation_id: int
    question_message_id: int | None
    answer_message_id: int | None
    replace_answer_message_id: int | None
    feedback_id: int | None
    status: str
    frontend_request_id: str | None
    backend_task_id: str | None
    worker_id: str | None
    dispatch_attempts: int
    claimed_at: datetime | None
    lease_expires_at: datetime | None
    model_name: str | None
    error_message: str | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GenerationTaskListData(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[GenerationTaskOut]


class ModelFailureCallbackIn(BaseModel):
    conversation_id: int
    generation_task_id: int | None = None
    backend_task_id: str | None = Field(default=None, max_length=64)
    model_name: str | None = Field(default=None, max_length=64)
    error_message: str = Field(min_length=1, max_length=500)


class MessageFeedbackCreate(BaseModel):
    rating: str = Field(pattern="^(like|dislike)$")
    reason: str | None = Field(default=None, max_length=128)
    detail: str | None = Field(default=None, max_length=5000)
    request_id: str | None = Field(default=None, max_length=64)
    regenerate: bool = False


class MessageFeedbackOut(BaseModel):
    id: int
    conversation_id: int
    message_id: int
    user_id: int
    rating: str
    reason: str | None
    detail: str | None
    request_id: str | None
    regenerate_task_id: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BackendTaskClaimRequest(BaseModel):
    worker_id: str | None = Field(default=None, max_length=64)
    model_name: str | None = Field(default=None, max_length=64)
    backend_task_id: str | None = Field(default=None, max_length=64)
    conversation_id: int | None = Field(default=None, ge=1)
    lease_seconds: int | None = Field(default=None, ge=30, le=3600)


class BackendTaskClaimData(BaseModel):
    task_id: int
    backend_task_id: str
    conversation_id: int
    question_message_id: int
    replace_answer_message_id: int | None
    feedback_id: int | None
    feedback_rating: str | None
    feedback_reason: str | None
    feedback_detail: str | None
    frontend_request_id: str | None
    question_text: str
    question_request_id: str | None
    question_meta_json: dict | None
    worker_id: str | None
    model_name: str | None
    claimed_at: datetime
    lease_expires_at: datetime
    dispatch_attempts: int


class BackendTaskHeartbeatRequest(BaseModel):
    worker_id: str | None = Field(default=None, max_length=64)
    lease_seconds: int | None = Field(default=None, ge=30, le=3600)
