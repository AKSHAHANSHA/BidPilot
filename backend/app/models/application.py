"""A vendor's application to a listing, and the documents submitted with it."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.enums import (
    ApplicationStatus,
    DocumentExtractionStatus,
    RequiredDocumentType,
)
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.listing import TenderListing
    from app.models.organisation import Organisation
    from app.models.screening import ApplicationScreening


class Application(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "applications"
    __table_args__ = (
        # The applying organisation must belong to the applying user.
        ForeignKeyConstraint(
            ["vendor_organisation_id", "vendor_user_id"],
            ["organisations.id", "organisations.owner_user_id"],
            name="fk_applications_vendor_organisation_owner",
            ondelete="CASCADE",
        ),
        # One application per vendor per listing. A vendor who wants to change their bid edits
        # the draft they already have; letting them stack submissions would make the buyer's
        # applicant list ambiguous and the score meaningless.
        UniqueConstraint("listing_id", "vendor_user_id", name="uq_applications_listing_vendor"),
        # Supports the composite foreign key on application_documents.
        UniqueConstraint("id", "vendor_user_id", name="uq_applications_id_vendor_user_id"),
        CheckConstraint(f"status IN ({ApplicationStatus.sql_in_list()})", name="status"),
        CheckConstraint("bid_amount IS NULL OR bid_amount >= 0", name="bid_amount_positive"),
        CheckConstraint(
            "estimated_cost IS NULL OR estimated_cost >= 0", name="estimated_cost_positive"
        ),
        CheckConstraint(
            "proposed_duration_months IS NULL OR proposed_duration_months > 0",
            name="proposed_duration_positive",
        ),
        # A draft has not been submitted; anything else has. Keeps the vendor dashboard's
        # "applied" count honest without a second source of truth.
        CheckConstraint(
            "status = 'draft' OR submitted_at IS NOT NULL",
            name="submitted_needs_timestamp",
        ),
        CheckConstraint(
            "status NOT IN ('approved', 'rejected') OR decided_at IS NOT NULL",
            name="decided_needs_timestamp",
        ),
        Index("ix_applications_vendor_status", "vendor_user_id", "status"),
        Index("ix_applications_listing_status", "listing_id", "status"),
        Index("ix_applications_vendor_submitted", "vendor_user_id", "submitted_at"),
    )

    listing_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tender_listings.id", ondelete="CASCADE"),
        nullable=False,
    )
    vendor_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    vendor_organisation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ApplicationStatus.DRAFT.value
    )

    cover_letter: Mapped[str | None] = mapped_column(Text, default=None)
    #: What the vendor is charging. Numeric for the same reason as the listing budget.
    bid_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)
    #: What the vendor expects it to cost them. Private to the vendor — never serialised into
    #: any buyer-facing schema — and the basis of the margin figure on their own dashboard.
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)
    proposed_duration_months: Mapped[int | None] = mapped_column(SmallInteger, default=None)

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    #: The buyer's stated reason. Shown to the vendor verbatim, so it is their words, not ours.
    decision_note: Mapped[str | None] = mapped_column(Text, default=None)
    #: Set when the buyer first opens the application — this is what separates "waiting for an
    #: answer" from "they have not looked at it yet".
    first_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    listing: Mapped[TenderListing] = relationship(back_populates="applications")
    vendor_organisation: Mapped[Organisation] = relationship(back_populates="applications")
    documents: Mapped[list[ApplicationDocument]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    screening: Mapped[ApplicationScreening | None] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )

    @property
    def margin_amount(self) -> Decimal | None:
        """Bid minus expected cost. Derived, never stored — a stored copy would go stale the
        first time a vendor revised either figure."""
        if self.bid_amount is None or self.estimated_cost is None:
            return None
        return self.bid_amount - self.estimated_cost

    def __repr__(self) -> str:
        return f"<Application id={self.id} status={self.status}>"


class ApplicationDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A file the vendor attached to their application.

    Mirrors `Document` deliberately — same content-addressed storage key, same SHA-256
    duplicate rule, same extraction vocabulary — because both are fed to the same extraction
    code. What differs is ownership: this one hangs off an application, not a tender.
    """

    __tablename__ = "application_documents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["application_id", "vendor_user_id"],
            ["applications.id", "applications.vendor_user_id"],
            name="fk_application_documents_application_vendor",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "application_id", "sha256", name="uq_application_documents_application_sha256"
        ),
        UniqueConstraint("storage_key", name="uq_application_documents_storage_key"),
        CheckConstraint(
            f"extraction_status IN ({DocumentExtractionStatus.sql_in_list()})",
            name="extraction_status",
        ),
        CheckConstraint(
            f"declared_document_type IS NULL "
            f"OR declared_document_type IN ({RequiredDocumentType.sql_in_list()})",
            name="declared_document_type",
        ),
        CheckConstraint(
            f"detected_document_type IS NULL "
            f"OR detected_document_type IN ({RequiredDocumentType.sql_in_list()})",
            name="detected_document_type",
        ),
        CheckConstraint("size_bytes > 0", name="size_positive"),
        Index("ix_application_documents_application", "application_id"),
        Index("ix_application_documents_vendor", "vendor_user_id"),
    )

    application_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    vendor_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    #: Display only. Truncated, never trusted as a path component.
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(80), nullable=False)
    #: "{vendor_user_id}/applications/{application_id}/{stored_filename}".
    storage_key: Mapped[str] = mapped_column(String(200), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, default=None)
    extraction_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DocumentExtractionStatus.PENDING.value
    )

    #: What the vendor said this file is. A hint for screening, never the verdict — a vendor
    #: could label an expired licence as a current one, deliberately or by accident.
    declared_document_type: Mapped[str | None] = mapped_column(String(48), default=None)
    #: What screening concluded it actually is, from the extracted text.
    detected_document_type: Mapped[str | None] = mapped_column(String(48), default=None)

    application: Mapped[Application] = relationship(back_populates="documents")

    def __repr__(self) -> str:
        return f"<ApplicationDocument id={self.id} status={self.extraction_status}>"
