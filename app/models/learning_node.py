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


class LearningNodeType(str, Enum):
    lesson = "lesson"
    checkpoint = "checkpoint"
    practice = "practice"
    resource = "resource"
    other = "other"


class LearningNode(Base, TimestampMixin):
    __tablename__ = "learning_nodes"
    __table_args__ = (
        UniqueConstraint("path_id", "node_code", name="uq_learning_nodes_path_code"),
        Index("ix_learning_nodes_path_sort", "path_id", "sort_no"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
        },
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    path_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("learning_paths.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_code: Mapped[str] = mapped_column(String(64), nullable=False)
    parent_node_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("learning_nodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    node_type: Mapped[LearningNodeType] = mapped_column(
        SqlEnum(LearningNodeType, native_enum=False, length=20),
        nullable=False,
        default=LearningNodeType.lesson,
        index=True,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    est_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sort_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unlock_rule_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    content_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    path = relationship("LearningPath", back_populates="nodes")

