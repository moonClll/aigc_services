from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import BigInteger, DateTime, Enum as SqlEnum, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class MessageRole(str, Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


class MessageType(str, Enum):
    question = "question"
    answer = "answer"
    feedback = "feedback"
    system = "system"


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
        },
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[MessageRole] = mapped_column(
        SqlEnum(MessageRole, native_enum=False, length=20),
        nullable=False,
        default=MessageRole.user,
        index=True,
    )
    message_type: Mapped[MessageType] = mapped_column(
        SqlEnum(MessageType, native_enum=False, length=20),
        nullable=False,
        default=MessageType.question,
        index=True,
    )
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    request_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        unique=True,
        index=True,
    )
    parent_message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    meta_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
    )

    conversation = relationship("Conversation", back_populates="messages")
    parent = relationship("Message", remote_side=[id], uselist=False)
    assets = relationship(
        "MessageAsset",
        back_populates="message",
        cascade="all, delete-orphan",
    )
