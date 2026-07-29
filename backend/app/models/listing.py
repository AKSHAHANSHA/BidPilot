"""A published tender opportunity and the document checklist a bidder must satisfy.

A `TenderListing` is what the public catalogue shows and what a vendor applies to. It is a
different thing from `Tender`, which is a *vendor's private workspace* for analysing a tender
document they found somewhere. Keeping them apart means the public feed can never accidentally
expose a vendor's own uploads, and neither model has to carry columns that are meaningless on
the other side of the marketplace.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.enums import Emirate, ListingStatus, RequiredDocumentType, TenderCategory
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.application import Application
    from app.models.organisation import Organisation

#: Same mutable-array treatment as `CompanyProfile`: without it an in-place `append` is
#: invisible to the unit of work and silently fails to persist.
StringArray = MutableList.as_mutable(ARRAY(Text))

MAX_SUMMARY_LENGTH = 400
MAX_DESCRIPTION_LENGTH = 20000


class TenderListing(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tender_listings"
    __table_args__ = (
        # The listing's organisation must belong to the listing's owner. Expressed as a
        # composite foreign key so the invariant survives any code path, including scripts.
        ForeignKeyConstraint(
            ["organisation_id", "owner_user_id"],
            ["organisations.id", "organisations.owner_user_id"],
            name="fk_tender_listings_organisation_owner",
            ondelete="CASCADE",
        ),
        UniqueConstraint("id", "owner_user_id", name="uq_tender_listings_id_owner_user_id"),
        # A buyer's own reference must be unique within their organisation, not globally:
        # two authorities can legitimately both run a tender called "PW-2026-001".
        UniqueConstraint(
            "organisation_id", "reference", name="uq_tender_listings_organisation_reference"
        ),
        CheckConstraint(f"status IN ({ListingStatus.sql_in_list()})", name="status"),
        CheckConstraint(f"category IN ({TenderCategory.sql_in_list()})", name="category"),
        CheckConstraint(f"emirate IN ({Emirate.sql_in_list()})", name="emirate"),
        CheckConstraint("budget_min IS NULL OR budget_min >= 0", name="budget_min_positive"),
        CheckConstraint("budget_max IS NULL OR budget_max >= 0", name="budget_max_positive"),
        CheckConstraint(
            "budget_min IS NULL OR budget_max IS NULL OR budget_min <= budget_max",
            name="budget_range",
        ),
        # A published listing without a deadline is unbiddable: the vendor cannot know when to
        # submit and the closing job has nothing to act on. Drafts are exempt so a buyer can
        # save work in progress.
        CheckConstraint(
            "status = 'draft' OR submission_deadline IS NOT NULL",
            name="published_needs_deadline",
        ),
        CheckConstraint(
            "status = 'draft' OR published_at IS NOT NULL",
            name="published_needs_timestamp",
        ),
        CheckConstraint(
            "min_years_experience IS NULL OR min_years_experience >= 0",
            name="min_years_experience_positive",
        ),
        CheckConstraint(
            "bid_bond_percentage IS NULL OR bid_bond_percentage BETWEEN 0 AND 100",
            name="bid_bond_percentage_range",
        ),
        CheckConstraint("application_count >= 0", name="application_count_positive"),
        # The public catalogue's default query: published listings, soonest deadline first.
        Index("ix_tender_listings_status_deadline", "status", "submission_deadline"),
        Index("ix_tender_listings_status_category", "status", "category"),
        Index("ix_tender_listings_status_emirate", "status", "emirate"),
        Index("ix_tender_listings_owner_status", "owner_user_id", "status"),
        Index("ix_tender_listings_organisation", "organisation_id"),
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    organisation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    # --- What it is ---
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    #: One-paragraph pitch shown on the catalogue card. Kept separate from `description` so the
    #: card never has to truncate mid-sentence on arbitrary prose.
    summary: Mapped[str] = mapped_column(String(MAX_SUMMARY_LENGTH), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reference: Mapped[str | None] = mapped_column(String(120), default=None)
    category: Mapped[str] = mapped_column(String(48), nullable=False)
    #: Free-text refinement under the controlled category, e.g. "district cooling".
    industry: Mapped[str | None] = mapped_column(String(120), default=None)
    tags: Mapped[list[str]] = mapped_column(StringArray, nullable=False, default=list)

    # --- Where ---
    emirate: Mapped[str] = mapped_column(String(32), nullable=False)
    city: Mapped[str | None] = mapped_column(String(120), default=None)

    # --- Money ---
    #: Numeric, never float — these are compared against vendor bid amounts, where binary
    #: rounding error is unacceptable. Both nullable: many public tenders do not disclose.
    budget_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)
    budget_max: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="AED")

    # --- When ---
    #: Timezone-aware: compared against `now()` for the "closing soon" badge and the close job.
    submission_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    questions_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    contract_duration_months: Mapped[int | None] = mapped_column(SmallInteger, default=None)

    # --- Eligibility ---
    min_years_experience: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    required_certifications: Mapped[list[str]] = mapped_column(
        StringArray, nullable=False, default=list
    )
    requires_bid_bond: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bid_bond_percentage: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), default=None)

    # --- Presentation ---
    #: Relative path or absolute URL for the card image. Rendered in an <img>, never executed.
    cover_image_url: Mapped[str | None] = mapped_column(String(500), default=None)

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ListingStatus.DRAFT.value
    )
    #: Denormalised counter maintained by the application service. The card grid renders
    #: hundreds of listings at once and a correlated count per row is the obvious way to make
    #: that query slow; the authoritative number is always `count(applications)`.
    application_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)

    organisation: Mapped[Organisation] = relationship(back_populates="listings")
    document_requirements: Mapped[list[ListingDocumentRequirement]] = relationship(
        back_populates="listing",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ListingDocumentRequirement.display_order",
    )
    applications: Mapped[list[Application]] = relationship(
        back_populates="listing",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<TenderListing id={self.id} status={self.status} category={self.category}>"


class ListingDocumentRequirement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One entry on the checklist a bidder's submission is screened against.

    The buyer builds this list; screening produces exactly one finding per row. That one-to-one
    correspondence is why `document_type` is a controlled vocabulary rather than free text — a
    requirement the classifier has never heard of would score every vendor as missing it.
    """

    __tablename__ = "listing_document_requirements"
    __table_args__ = (
        UniqueConstraint(
            "listing_id", "document_type", name="uq_listing_document_requirements_listing_type"
        ),
        CheckConstraint(
            f"document_type IN ({RequiredDocumentType.sql_in_list()})", name="document_type"
        ),
        # Bounded so one requirement cannot be weighted into dominating the whole score.
        CheckConstraint("weight BETWEEN 1 AND 10", name="weight_range"),
        Index("ix_listing_document_requirements_listing", "listing_id"),
    )

    listing_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tender_listings.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_type: Mapped[str] = mapped_column(String(48), nullable=False)
    #: Mandatory items gate the submission; optional ones only move the score.
    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: Relative importance within its band. Defaults to 1 so a buyer who ignores the field
    #: gets a plain proportion of requirements met.
    weight: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    #: Buyer's own wording, e.g. "valid for at least 90 days beyond the closing date".
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    display_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)

    listing: Mapped[TenderListing] = relationship(back_populates="document_requirements")

    def __repr__(self) -> str:
        return (
            f"<ListingDocumentRequirement id={self.id} type={self.document_type} "
            f"mandatory={self.is_mandatory}>"
        )
