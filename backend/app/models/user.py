"""The account that owns every record in the system."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.enums import AccountType
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.notification import Notification
    from app.models.organisation import Organisation
    from app.models.password_reset import PasswordResetToken
    from app.models.refresh_session import RefreshSession


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        # The application lower-cases before insert; this makes the invariant the database's
        # rule too, so a future script or manual fix cannot create a duplicate-by-case account.
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint(f"account_type IN ({AccountType.sql_in_list()})", name="account_type"),
    )

    #: Stored lower-cased so the unique constraint is genuinely case-insensitive; a database
    #: `UNIQUE` on raw text would happily accept both "A@b.test" and "a@b.test".
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    #: Which side of the marketplace this account is on. Chosen at registration and never
    #: changed: an account's listings and applications would be nonsense if its side could
    #: flip, and `Organisation.account_type` caches this value on the assumption it cannot.
    #: Accounts created before the marketplace are backfilled as `vendor`, which is what they
    #: were — the original product was a single bidder analysing tenders sent to them.
    account_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default=AccountType.VENDOR.value
    )

    sessions: Mapped[list[RefreshSession]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    organisation: Mapped[Organisation | None] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    password_reset_tokens: Mapped[list[PasswordResetToken]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    notifications: Mapped[list[Notification]] = relationship(
        back_populates="recipient",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        # Deliberately excludes the email: repr output reaches logs and debuggers.
        return f"<User id={self.id} active={self.is_active}>"
