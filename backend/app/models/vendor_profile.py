"""Lightweight vendor identity for the marketplace layer.

Distinct from `CompanyProfile` (which stays the deep capability record used by the
bid-readiness pipeline). A vendor may still fill in a CompanyProfile later to power the
AI self-check; the VendorProfile only carries what's needed to render a browsable
marketplace card and identify the applicant.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class VendorProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "vendor_profiles"
    __table_args__ = (UniqueConstraint("owner_user_id", name="uq_vendor_profiles_owner_user_id"),)

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str | None] = mapped_column(String(120), default=None)
    primary_category: Mapped[str | None] = mapped_column(String(80), default=None)
    bio: Mapped[str | None] = mapped_column(Text, default=None)
    contact_email: Mapped[str | None] = mapped_column(String(320), default=None)
    contact_phone: Mapped[str | None] = mapped_column(String(40), default=None)

    def __repr__(self) -> str:
        return f"<VendorProfile id={self.id} owner_user_id={self.owner_user_id}>"
