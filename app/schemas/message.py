from datetime import datetime
from typing import Any
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class QuestionCreate(BaseModel):
    conversation_id: int
    content_text: str = Field(min_length=1, max_length=8000)
    request_id: str | None = Field(default=None, max_length=64)


AssetType = Literal["image", "mindmap", "file", "audio", "video", "other"]


class MessageAssetIn(BaseModel):
    asset_type: AssetType
    asset_url: str = Field(min_length=1, max_length=1024)
    mime_type: str | None = Field(default=None, max_length=128)
    title: str | None = Field(default=None, max_length=255)
    sort_no: int = Field(default=0, ge=0, le=100000)
    meta_json: dict[str, Any] | None = None


class MessageAssetOut(BaseModel):
    id: int
    message_id: int
    asset_type: str
    asset_url: str
    mime_type: str | None
    title: str | None
    sort_no: int
    meta_json: dict[str, Any] | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageOut(BaseModel):
    id: int
    conversation_id: int
    role: str
    message_type: str
    content_text: str
    request_id: str | None
    parent_message_id: int | None
    meta_json: dict[str, Any] | None
    created_at: datetime
    assets: list[MessageAssetOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class MessageListData(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[MessageOut]


class ModelAnswerCallbackIn(BaseModel):
    conversation_id: int
    question_message_id: int | None = None
    generation_task_id: int | None = None
    backend_task_id: str | None = Field(default=None, max_length=64)
    model_name: str | None = Field(default=None, max_length=64)
    answer_text: str = Field(min_length=1, max_length=20000)
    answer_request_id: str | None = Field(default=None, max_length=64)
    assets: list[MessageAssetIn] = Field(default_factory=list)
    meta_json: dict[str, Any] | None = None
