"""A refresh token's server-side record — the thing that makes logout mean something."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class RefreshSession(UUIDPrimaryKeyMixin, Base):
    """One issued refresh token.

    The raw token is never stored. Rotation creates a new row and revokes the old one, so the
    table doubles as a session history: which sessions existed, when, and from where.
    """

    __tablename__ = "refresh_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        # Deleting a user must not leave usable credentials behind.
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    #: SHA-256 of the token. Unique so a presented token maps to at most one session.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    #: Truncated before storage; a client-controlled string is never trusted for length.
    user_agent: Mapped[str | None] = mapped_column(String(256), default=None)
    #: Keyed hash, never a raw address — see `app.core.security.hash_ip`.
    ip_hash: Mapped[str | None] = mapped_column(String(64), default=None)

    user: Mapped[User] = relationship(back_populates="sessions")

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    def is_expired(self, *, now: datetime | None = None) -> bool:
        return self.expires_at <= (now or datetime.now(tz=UTC))

    def is_usable(self, *, now: datetime | None = None) -> bool:
        return not self.is_revoked and not self.is_expired(now=now)

    def __repr__(self) -> str:
        return f"<RefreshSession id={self.id} user_id={self.user_id} revoked={self.is_revoked}>"
