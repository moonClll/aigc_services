from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import BigInteger, DateTime, Enum as SqlEnum, ForeignKey, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class MessageAssetType(str, Enum):
    image = "image"
    mindmap = "mindmap"
    file = "file"
    audio = "audio"
    video = "video"
    other = "other"


class MessageAsset(Base):
    __tablename__ = "message_assets"
    __table_args__ = (
        Index("ix_message_assets_message_sort", "message_id", "sort_no"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
        },
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_type: Mapped[MessageAssetType] = mapped_column(
        SqlEnum(MessageAssetType, native_enum=False, length=20),
        nullable=False,
        default=MessageAssetType.other,
        index=True,
    )
    asset_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sort_no: Mapped[int] = mapped_column(nullable=False, default=0)
    meta_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
    )

    message = relationship("Message", back_populates="assets")

