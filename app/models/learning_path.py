from enum import Enum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Enum as SqlEnum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class LearningPathStatus(str, Enum):
    active = "active"
    archived = "archived"


class LearningPath(Base, TimestampMixin):
    __tablename__ = "learning_paths"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "conversation_id",
            "version_no",
            name="uq_learning_paths_user_conversation_version",
        ),
        Index("ix_learning_paths_conversation_status", "conversation_id", "status"),
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
    conversation_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_task_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("generation_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="Learning Path")
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[LearningPathStatus] = mapped_column(
        SqlEnum(LearningPathStatus, native_enum=False, length=20),
        nullable=False,
        default=LearningPathStatus.active,
        index=True,
    )

    nodes = relationship(
        "LearningNode",
        back_populates="path",
        cascade="all, delete-orphan",
    )

