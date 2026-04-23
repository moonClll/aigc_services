from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=255)


class ConversationOut(BaseModel):
    id: int
    user_id: int
    title: str
    current_status: str
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationListData(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ConversationOut]


class ConversationTitleOut(BaseModel):
    id: int
    title: str
    last_message_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class ConversationTitleListData(BaseModel):
    total: int
    items: list[ConversationTitleOut]
