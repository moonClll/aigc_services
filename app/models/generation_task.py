from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, DateTime, Enum as SqlEnum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class GenerationTaskStatus(str, Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"


class GenerationTask(Base, TimestampMixin):
    __tablename__ = "generation_tasks"
    __table_args__ = (
        Index("ix_generation_tasks_conversation_status", "conversation_id", "status"),
        Index("ix_generation_tasks_status_lease", "status", "lease_expires_at"),
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
    question_message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    answer_message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    replace_answer_message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    feedback_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("feedbacks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[GenerationTaskStatus] = mapped_column(
        SqlEnum(GenerationTaskStatus, native_enum=False, length=20),
        nullable=False,
        default=GenerationTaskStatus.pending,
        index=True,
    )
    frontend_request_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    backend_task_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        unique=True,
        index=True,
    )
    worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    dispatch_attempts: Mapped[int] = mapped_column(nullable=False, default=0)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
    )
    model_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
