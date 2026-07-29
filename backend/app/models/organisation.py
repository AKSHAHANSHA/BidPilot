"""The registering organisation behind an account — buyer or supplier.

One row per user, created during registration. This is deliberately *not* `CompanyProfile`:
that model is a vendor's deep capability dossier (licence activities, revenue bands, coverage)
built up over time to feed evidence matching, and every field it demands would be an absurd
thing to ask for on a sign-up form. `Organisation` is the small, always-present identity a
listing card or an applicant row needs — name, where they are, how to reach them.

A vendor therefore has both: an `Organisation` from the moment they register, and a
`CompanyProfile` once they start preparing bids.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.enums import AccountType, Emirate
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.application import Application
    from app.models.listing import TenderListing
    from app.models.user import User

MAX_DESCRIPTION_LENGTH = 4000

#: Matches `CompanyProfile`'s bounds so the two never disagree about a plausible year.
MIN_YEAR_ESTABLISHED = 1800
MAX_YEAR_ESTABLISHED = 2200


class Organisation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organisations"
    __table_args__ = (
        # One organisation per account, guaranteed by the database rather than by a service
        # check that a concurrent double-POST would race straight past.
        UniqueConstraint("owner_user_id", name="uq_organisations_owner_user_id"),
        # Lets children carry the composite foreign key that makes cross-account rows
        # unrepresentable (the ownership pattern from docs/08 D27).
        UniqueConstraint("id", "owner_user_id", name="uq_organisations_id_owner_user_id"),
        CheckConstraint(f"account_type IN ({AccountType.sql_in_list()})", name="account_type"),
        CheckConstraint(f"emirate IN ({Emirate.sql_in_list()})", name="emirate"),
        CheckConstraint(
            f"year_established IS NULL "
            f"OR year_established BETWEEN {MIN_YEAR_ESTABLISHED} AND {MAX_YEAR_ESTABLISHED}",
            name="year_established",
        ),
        CheckConstraint(
            "employee_count IS NULL OR employee_count >= 0", name="employee_count_positive"
        ),
        Index("ix_organisations_account_type", "account_type"),
        Index("ix_organisations_emirate", "emirate"),
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    #: Copied from the owning user at registration and never updated. Denormalised because the
    #: public listing feed reads organisations without touching `users`, and a side that could
    #: drift would silently mislabel every card. `AccountType` is immutable on the user for the
    #: same reason, so the copy cannot go stale.
    account_type: Mapped[str] = mapped_column(String(16), nullable=False)

    # --- Identity ---
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    industry: Mapped[str | None] = mapped_column(String(120), default=None)
    #: Trade licence or commercial registration number. Free text: the format varies by
    #: emirate and by authority, and rejecting an unfamiliar-but-valid one helps nobody.
    registration_number: Mapped[str | None] = mapped_column(String(100), default=None)

    # --- Location ---
    emirate: Mapped[str] = mapped_column(String(32), nullable=False)
    city: Mapped[str | None] = mapped_column(String(120), default=None)
    address_line: Mapped[str | None] = mapped_column(String(255), default=None)
    country: Mapped[str] = mapped_column(
        String(100), nullable=False, default="United Arab Emirates"
    )

    # --- Contact ---
    contact_email: Mapped[str] = mapped_column(String(320), nullable=False)
    contact_phone: Mapped[str | None] = mapped_column(String(40), default=None)
    website: Mapped[str | None] = mapped_column(String(255), default=None)

    # --- Scale (optional: a new supplier may not want to disclose these) ---
    year_established: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    employee_count: Mapped[int | None] = mapped_column(Integer, default=None)

    #: Set by an administrator out of band. Surfaced as a badge, never used in scoring —
    #: an unverified organisation is not a worse bidder, only a less-checked one.
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    owner: Mapped[User] = relationship(back_populates="organisation")
    listings: Mapped[list[TenderListing]] = relationship(
        back_populates="organisation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    applications: Mapped[list[Application]] = relationship(
        back_populates="vendor_organisation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Organisation id={self.id} account_type={self.account_type}>"
