"""站内通知。余额预警在账本启用前不会生成。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint("kind IN ('security', 'key_expiry', 'balance')", name="ck_notifications_kind"),
        UniqueConstraint("user_id", "dedupe_key", name="uq_notifications_user_dedupe"),
        # 未读通知高并发拉取（部分索引，只覆盖未读，保持索引小）
        Index(
            "ix_notifications_user_unread",
            "user_id",
            "created_at",
            postgresql_where=text("read_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    related_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    dedupe_key: Mapped[str] = mapped_column(String(160), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    balance_alerts_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    warn_high: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False, default=Decimal("10"))
    warn_low: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False, default=Decimal("2"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
