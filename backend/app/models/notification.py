"""In-app notifications.

Deliberately a plain table read by polling rather than a push channel: a websocket fan-out
would be the single most complex thing in this application, and the dashboards already refetch
on an interval. Rows are written by services when something happens to a listing or an
application, and are addressed to one recipient.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.enums import NotificationType
from app.models.base import UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class Notification(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(f"type IN ({NotificationType.sql_in_list()})", name="type"),
        CheckConstraint(
            "screening_score IS NULL OR screening_score BETWEEN 0 AND 100",
            name="screening_score_range",
        ),
        # The unread badge and the notification list are the only two queries this table
        # serves; both start from the recipient.
        Index("ix_notifications_recipient_created", "recipient_user_id", "created_at"),
        Index("ix_notifications_recipient_unread", "recipient_user_id", "read_at"),
    )

    recipient_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    #: Deep-link targets. Both nullable and both `SET NULL`: a notification about a deleted
    #: listing should lose its link, not vanish from the recipient's history.
    listing_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tender_listings.id", ondelete="SET NULL"),
        default=None,
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("applications.id", ondelete="SET NULL"),
        default=None,
    )

    #: Denormalised onto the notification so the buyer's list shows the score without a join
    #: through application → screening for every row. Null for types that carry no score.
    screening_score: Mapped[int | None] = mapped_column(SmallInteger, default=None)

    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    recipient: Mapped[User] = relationship(back_populates="notifications")

    @property
    def is_read(self) -> bool:
        return self.read_at is not None

    def __repr__(self) -> str:
        return f"<Notification id={self.id} type={self.type} read={self.is_read}>"
