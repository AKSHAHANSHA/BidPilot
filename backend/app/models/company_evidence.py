"""A document or claim supporting a company capability.

Only user-verified evidence counts as approved when matching tender requirements
(`docs/03_AI_PIPELINE_AND_SCORING.md` §8).

**No file columns yet.** Phase 3 owns upload. Adding nullable storage columns, or a nullable
foreign key to a future `documents` table, is purely additive — neither is a destructive
migration — so inventing them now would be speculation. The API response carries a
contract-stable `attachment: null` field instead, which keeps the frontend contract unchanged
when Phase 3 lands.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.enums import EvidenceCategory, VerificationStatus
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.company_profile import CompanyProfile

StringArray = MutableList.as_mutable(ARRAY(Text))

MAX_DESCRIPTION_LENGTH = 4000
MAX_TAGS = 20


class CompanyEvidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "company_evidence"
    __table_args__ = (
        # The composite foreign key is the point of this table's design: it makes "you cannot
        # attach evidence to another user's profile" a database guarantee rather than a check
        # some future route might forget. An attacker supplying a valid profile ID they do not
        # own cannot satisfy (company_profile_id, owner_user_id) together.
        ForeignKeyConstraint(
            ["company_profile_id", "owner_user_id"],
            ["company_profiles.id", "company_profiles.owner_user_id"],
            name="fk_company_evidence_profile_owner",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            f"category IN ({EvidenceCategory.sql_in_list()})",
            name="category",
        ),
        CheckConstraint(
            f"verification_status IN ({VerificationStatus.sql_in_list()})",
            name="verification_status",
        ),
        CheckConstraint(
            "issue_date IS NULL OR expiry_date IS NULL OR issue_date <= expiry_date",
            name="date_order",
        ),
        CheckConstraint(f"cardinality(tags) <= {MAX_TAGS}", name="tag_count"),
        # Postgres does not index foreign keys automatically, and this pair is on the join path
        # for every owned lookup.
        Index("ix_company_evidence_profile_owner", "company_profile_id", "owner_user_id"),
        Index("ix_company_evidence_owner_category", "owner_user_id", "category"),
        Index("ix_company_evidence_owner_status", "owner_user_id", "verification_status"),
        # Supports expiry-state filtering without a full scan.
        Index("ix_company_evidence_expiry_date", "expiry_date"),
        # GIN for tag containment (`tags @> ARRAY['iso']`).
        Index("ix_company_evidence_tags", "tags", postgresql_using="gin"),
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    company_profile_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    issuing_organisation: Mapped[str | None] = mapped_column(String(255), default=None)
    reference_number: Mapped[str | None] = mapped_column(String(120), default=None)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    issue_date: Mapped[date | None] = mapped_column(Date, default=None)
    expiry_date: Mapped[date | None] = mapped_column(Date, default=None)

    verification_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=VerificationStatus.UNVERIFIED.value
    )
    verification_notes: Mapped[str | None] = mapped_column(Text, default=None)

    tags: Mapped[list[str]] = mapped_column(StringArray, nullable=False, default=list)

    company_profile: Mapped[CompanyProfile] = relationship(back_populates="evidence")

    def __repr__(self) -> str:
        return f"<CompanyEvidence id={self.id} category={self.category}>"
