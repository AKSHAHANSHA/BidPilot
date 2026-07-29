"""A password-reset token's server-side record.

Same shape and the same reasoning as `RefreshSession`: the raw token is never stored, only its
SHA-256, so a database disclosure does not hand an attacker a working reset link. Tokens are
single-use and short-lived, and consuming one revokes every live session for that account —
resetting a password is exactly the moment a user wants any hijacked session dropped.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class PasswordResetToken(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "password_reset_tokens"
    __table_args__ = (
        # Expiring old tokens for a user is a range scan over this pair.
        Index("ix_password_reset_tokens_user_expires", "user_id", "expires_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    #: SHA-256 of the token. Unique so a presented token maps to at most one record.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Set the moment the token is spent, which is what makes it single-use.
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    #: Keyed hash, never a raw address — see `app.core.security.hash_ip`.
    requested_ip_hash: Mapped[str | None] = mapped_column(String(64), default=None)

    user: Mapped[User] = relationship(back_populates="password_reset_tokens")

    @property
    def is_used(self) -> bool:
        return self.used_at is not None

    def is_expired(self, *, now: datetime | None = None) -> bool:
        return self.expires_at <= (now or datetime.now(tz=UTC))

    def is_usable(self, *, now: datetime | None = None) -> bool:
        return not self.is_used and not self.is_expired(now=now)

    def __repr__(self) -> str:
        return f"<PasswordResetToken id={self.id} user_id={self.user_id} used={self.is_used}>"
