from datetime import datetime
from enum import Enum

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class LearningNodeStateValue(str, Enum):
    locked = "locked"
    available = "available"
    in_progress = "in_progress"
    done = "done"


class LearningNodeState(Base, TimestampMixin):
    __tablename__ = "learning_node_states"
    __table_args__ = (
        UniqueConstraint("user_id", "path_id", "node_id", name="uq_learning_node_states_user_path_node"),
        Index("ix_learning_node_states_user_path", "user_id", "path_id"),
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
    path_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("learning_paths.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("learning_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    state: Mapped[LearningNodeStateValue] = mapped_column(
        SqlEnum(LearningNodeStateValue, native_enum=False, length=20),
        nullable=False,
        default=LearningNodeStateValue.locked,
        index=True,
    )
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

