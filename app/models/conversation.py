from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, DateTime, Enum as SqlEnum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ConversationStatus(str, Enum):
    active = "active"
    archived = "archived"


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_user_last_message", "user_id", "last_message_at"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
        },
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="New Conversation",
    )
    current_status: Mapped[ConversationStatus] = mapped_column(
        SqlEnum(ConversationStatus, native_enum=False, length=20),
        nullable=False,
        default=ConversationStatus.active,
        index=True,
    )
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
    )

    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation")
