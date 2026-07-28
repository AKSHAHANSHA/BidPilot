"""A simple in-app notification for the marketplace layer.

Deliberately minimal — no delivery adapter (email/push/websockets); the frontend polls
`GET /notifications` and shows an unread badge. `payload` is a small JSONB blob so the UI
can render each kind with just its own data.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.domain.enums import NotificationKind
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Notification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(f"kind IN ({NotificationKind.sql_in_list()})", name="notification_kind"),
        Index("ix_notifications_recipient_read", "recipient_user_id", "read_at"),
    )

    recipient_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(String(1000), default=None)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    def __repr__(self) -> str:
        return f"<Notification id={self.id} kind={self.kind} read={self.read_at is not None}>"
