"""The result of screening a submission's documents against a listing's checklist.

Division of labour, following `docs/03` and the hard rule in `CLAUDE.md`: the model reads
extracted document text and proposes *which requirement each file satisfies*, with a page and a
quote to prove it. Python then counts those validated findings and computes the score. The model
never produces the number.
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
    AnalysisErrorCode,
    DocumentScreeningVerdict,
    RequiredDocumentType,
    ScreeningStatus,
)
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.application import Application


class ApplicationScreening(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "application_screenings"
    __table_args__ = (
        # One screening per application. Re-screening overwrites this row and replaces its
        # findings, so the buyer's applicant list can never show two competing scores.
        UniqueConstraint("application_id", name="uq_application_screenings_application_id"),
        CheckConstraint(f"status IN ({ScreeningStatus.sql_in_list()})", name="status"),
        CheckConstraint(
            f"error_code IS NULL OR error_code IN ({AnalysisErrorCode.sql_in_list()})",
            name="error_code",
        ),
        CheckConstraint(
            "overall_score IS NULL OR overall_score BETWEEN 0 AND 100", name="score_range"
        ),
        # A score only means something once the run finished. Enforcing the pairing here stops
        # a half-written row from being read as a real result (`CLAUDE.md`: no fake progress).
        CheckConstraint(
            "status = 'completed' OR overall_score IS NULL",
            name="score_only_when_completed",
        ),
        CheckConstraint(
            "status <> 'completed' OR completed_at IS NOT NULL",
            name="completed_needs_timestamp",
        ),
        CheckConstraint("mandatory_met >= 0 AND mandatory_total >= 0", name="mandatory_counts"),
        CheckConstraint("optional_met >= 0 AND optional_total >= 0", name="optional_counts"),
        CheckConstraint("mandatory_met <= mandatory_total", name="mandatory_met_bounded"),
        CheckConstraint("optional_met <= optional_total", name="optional_met_bounded"),
        Index("ix_application_screenings_status", "status"),
        Index("ix_application_screenings_score", "overall_score"),
    )

    application_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ScreeningStatus.PENDING.value
    )

    #: 0-100, computed in Python from the findings below. Null until the run completes.
    overall_score: Mapped[int | None] = mapped_column(SmallInteger, default=None)

    mandatory_met: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    mandatory_total: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    optional_met: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    optional_total: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)

    documents_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages_extracted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: How many pages needed OCR because they carried no extractable text layer. Surfaced to
    #: the vendor: a submission that was mostly photographs is a fixable upload problem.
    pages_needing_ocr: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: Advisory narrative, generated from the validated findings — never from raw document
    #: text (`CLAUDE.md`: narrative reports use validated structured records).
    summary: Mapped[str | None] = mapped_column(Text, default=None)

    scoring_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1.0.0")
    prompt_version: Mapped[str | None] = mapped_column(String(16), default=None)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    #: Safe, machine-readable reason. Developer detail stays in the logs.
    error_code: Mapped[str | None] = mapped_column(String(32), default=None)

    application: Mapped[Application] = relationship(back_populates="screening")
    findings: Mapped[list[ScreeningFinding]] = relationship(
        back_populates="screening",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ScreeningFinding.display_order",
    )

    @property
    def has_blocking_gap(self) -> bool:
        """True when a mandatory requirement is unmet — the buyer's first-glance filter."""
        return self.mandatory_met < self.mandatory_total

    def __repr__(self) -> str:
        return (
            f"<ApplicationScreening id={self.id} status={self.status} score={self.overall_score}>"
        )


class ScreeningFinding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One requirement's verdict, with the evidence that justifies it.

    Exactly one row per `ListingDocumentRequirement` on the listing. A requirement with no
    matching upload still gets a row, with verdict `missing` — the absence is the finding, and
    silently omitting it would leave the buyer unable to tell "not required" from "not supplied".
    """

    __tablename__ = "screening_findings"
    __table_args__ = (
        UniqueConstraint(
            "screening_id", "document_type", name="uq_screening_findings_screening_type"
        ),
        CheckConstraint(
            f"document_type IN ({RequiredDocumentType.sql_in_list()})", name="document_type"
        ),
        CheckConstraint(f"verdict IN ({DocumentScreeningVerdict.sql_in_list()})", name="verdict"),
        CheckConstraint("weight BETWEEN 1 AND 10", name="weight_range"),
        CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0 AND 1", name="confidence_range"
        ),
        CheckConstraint("source_page IS NULL OR source_page >= 1", name="source_page_positive"),
        # A "present" verdict has to point at something. Without this a hallucinated match
        # could raise a score with nothing behind it (`CLAUDE.md`: no material finding without
        # a verified source citation).
        CheckConstraint(
            "verdict NOT IN ('present', 'present_expired') OR matched_document_id IS NOT NULL",
            name="present_needs_document",
        ),
        Index("ix_screening_findings_screening", "screening_id"),
    )

    screening_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("application_screenings.id", ondelete="CASCADE"),
        nullable=False,
    )

    document_type: Mapped[str] = mapped_column(String(48), nullable=False)
    verdict: Mapped[str] = mapped_column(String(24), nullable=False)
    #: Copied from the requirement so a later edit to the checklist cannot retroactively
    #: change what this completed screening was actually measured against.
    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    weight: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)

    #: The upload that satisfied this requirement.
    #:
    #: `CASCADE`, not `SET NULL`. Nulling it looks gentler — keep the finding, forget the file —
    #: but it lands the row straight in `present_needs_document` below, which forbids a
    #: "supplied" verdict that names no document. Postgres applies the rule while deleting the
    #: document, so the check fires and the delete fails: with `SET NULL` an application whose
    #: screening found anything could not be deleted at all.
    #:
    #: Cascading is also the honest reading. A finding asserting "supplied, see page 4 of this
    #: file" is a claim *about* that file. Once the file is gone the claim has nothing behind
    #: it, and keeping it would be exactly the unevidenced material finding `CLAUDE.md` rules
    #: out. Documents are only deletable while the application is a draft, before any screening
    #: exists, so in practice this fires only when the whole application is being removed.
    matched_document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("application_documents.id", ondelete="CASCADE"),
        default=None,
    )
    #: The classifier's self-reported confidence. Advisory only — it never scales the score,
    #: because a model's confidence is not calibrated and multiplying by it would smuggle the
    #: model back into the arithmetic.
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), default=None)

    #: Provenance for the match: which page, and the text that proves it.
    source_page: Mapped[int | None] = mapped_column(Integer, default=None)
    evidence_quote: Mapped[str | None] = mapped_column(Text, default=None)

    #: Reviewer-facing explanation, e.g. "licence expires before the closing date".
    note: Mapped[str | None] = mapped_column(Text, default=None)
    display_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)

    screening: Mapped[ApplicationScreening] = relationship(back_populates="findings")

    def __repr__(self) -> str:
        return f"<ScreeningFinding id={self.id} type={self.document_type} verdict={self.verdict}>"
