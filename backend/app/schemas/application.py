"""Application schemas — a vendor's bid, seen from both sides of the marketplace.

`ApplicationRead` and `ApplicantRead` describe the same row for two different audiences and
are deliberately *not* related by inheritance. `estimated_cost` and the margin derived from it
are vendor-private (`docs/09_PORTAL_SPEC.md` §10 rule 8); inheriting the buyer's view from the
vendor's would mean one careless field addition leaks a bidder's cost base to the buyer they
are negotiating with. Two independent classes make that leak impossible to introduce by
accident.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.domain.enums import ApplicationStatus, DocumentExtractionStatus, RequiredDocumentType
from app.schemas.listing import ListingCard, label_for
from app.schemas.organisation import OrganisationSummary
from app.schemas.screening import ScreeningSummary

MAX_COVER_LETTER_LENGTH = 8000
MAX_DECISION_NOTE_LENGTH = 2000

#: Bounded to fit `Numeric(14, 2)`, and `Decimal` end to end — a bid compared against a budget
#: must not drift by a binary rounding error.
Money = Annotated[Decimal, Field(ge=0, le=Decimal("99999999999.99"), decimal_places=2)]


def _strip_optional(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None


# --- Write shapes -------------------------------------------------------------------------


class ApplicationCreate(BaseModel):
    """A new draft application against a published listing.

    `status` is absent: an application is born a draft and moves through `/submit` and
    `/withdraw`, which can enforce their preconditions. The buyer's decision has its own
    endpoint and its own schema.
    """

    model_config = ConfigDict(extra="forbid")

    listing_id: uuid.UUID
    cover_letter: Annotated[str | None, Field(max_length=MAX_COVER_LETTER_LENGTH)] = None
    bid_amount: Annotated[
        Money | None, Field(description="What the vendor is charging. Shown to the buyer.")
    ] = None
    estimated_cost: Annotated[
        Money | None,
        Field(
            description=(
                "What the vendor expects the work to cost them. Private to the vendor and "
                "never serialised into a buyer-facing response."
            )
        ),
    ] = None
    proposed_duration_months: Annotated[int | None, Field(ge=1, le=600)] = None

    @field_validator("cover_letter")
    @classmethod
    def _strip_cover_letter(cls, value: str | None) -> str | None:
        return _strip_optional(value)


class ApplicationUpdate(BaseModel):
    """Partial update of a draft. Omitted fields are left untouched."""

    model_config = ConfigDict(extra="forbid")

    cover_letter: Annotated[str | None, Field(max_length=MAX_COVER_LETTER_LENGTH)] = None
    bid_amount: Money | None = None
    estimated_cost: Money | None = None
    proposed_duration_months: Annotated[int | None, Field(ge=1, le=600)] = None

    @field_validator("cover_letter")
    @classmethod
    def _strip_cover_letter(cls, value: str | None) -> str | None:
        return _strip_optional(value)


class ApplicationDecision(BaseModel):
    """`PATCH /applications/{id}/decision` — the buyer's verdict.

    The status is restricted to the three a buyer may actually set. `withdrawn` belongs to the
    vendor, and `draft`/`submitted`/`under_review` are pipeline states, not decisions.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal[
        ApplicationStatus.SHORTLISTED,
        ApplicationStatus.APPROVED,
        ApplicationStatus.REJECTED,
    ]
    note: Annotated[
        str | None,
        Field(
            max_length=MAX_DECISION_NOTE_LENGTH,
            description="The buyer's stated reason. Shown to the vendor verbatim.",
        ),
    ] = None

    @field_validator("note")
    @classmethod
    def _strip_note(cls, value: str | None) -> str | None:
        return _strip_optional(value)


# --- Read shapes --------------------------------------------------------------------------


class ApplicationDocumentRead(BaseModel):
    """A file attached to an application. Metadata only — the bytes are fetched separately."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    original_filename: str
    mime_type: str
    size_bytes: int
    sha256: Annotated[
        str,
        Field(description="Content hash. Two identical uploads on one application are rejected."),
    ]
    page_count: int | None
    extraction_status: DocumentExtractionStatus
    declared_document_type: Annotated[
        RequiredDocumentType | None,
        Field(
            description="What the vendor said this file is. A hint for screening, never a verdict."
        ),
    ]
    detected_document_type: Annotated[
        RequiredDocumentType | None,
        Field(description="What screening concluded it actually is, from the extracted text."),
    ]
    created_at: datetime

    @computed_field(description="Human-readable form of `declared_document_type`.")  # type: ignore[prop-decorator]
    @property
    def declared_document_type_label(self) -> str | None:
        declared = self.declared_document_type
        return None if declared is None else label_for(declared)

    @computed_field(description="Human-readable form of `detected_document_type`.")  # type: ignore[prop-decorator]
    @property
    def detected_document_type_label(self) -> str | None:
        detected = self.detected_document_type
        return None if detected is None else label_for(detected)


class ApplicationRead(BaseModel):
    """The vendor's own view of their application.

    Carries `estimated_cost` and `margin_amount` because the vendor owns both. Never return
    this shape to a buyer — see `ApplicantRead`.

    `listing`, `documents`, and `screening` are populated from relationships, so the service
    must load them eagerly; a lazy load inside serialisation fails under async SQLAlchemy.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    listing_id: uuid.UUID
    listing: ListingCard
    status: ApplicationStatus
    cover_letter: str | None
    bid_amount: Decimal | None
    estimated_cost: Annotated[
        Decimal | None, Field(description="Vendor-private. Never appears in a buyer-facing schema.")
    ]
    margin_amount: Annotated[
        Decimal | None,
        Field(
            description=(
                "`bid_amount - estimated_cost`. Derived on read, null when either figure is "
                "missing, and negative when the bid is below cost."
            )
        ),
    ]
    proposed_duration_months: int | None
    submitted_at: datetime | None
    decided_at: datetime | None
    withdrawn_at: datetime | None
    decision_note: Annotated[
        str | None, Field(description="The buyer's reason, in the buyer's words.")
    ]
    documents: list[ApplicationDocumentRead]
    screening: ScreeningSummary | None
    created_at: datetime
    updated_at: datetime


class ApplicantRead(BaseModel):
    """The buyer's view of one applicant on their listing.

    Deliberately does not inherit from `ApplicationRead`. `estimated_cost` and
    `margin_amount` are absent by construction, so no future field on the vendor's view can
    reach a buyer through this schema (`docs/09` §10 rule 8).

    `vendor_organisation` is an `OrganisationSummary`: a buyer sees who bid and where they
    are, not the vendor's contact block.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    vendor_organisation: OrganisationSummary
    cover_letter: Annotated[str | None, Field(description="The vendor's pitch, written for you.")]
    bid_amount: Decimal | None
    proposed_duration_months: int | None
    status: ApplicationStatus
    submitted_at: datetime | None
    decided_at: datetime | None
    decision_note: str | None
    screening: Annotated[
        ScreeningSummary | None,
        Field(
            description=(
                "Null until the vendor submits and screening runs. Applicants are ranked by "
                "`overall_score`."
            )
        ),
    ]


# --- Dashboard aggregates -------------------------------------------------------------------


class VendorStats(BaseModel):
    """`GET /applications/stats` — the vendor dashboard's counters (`docs/09` §6).

    Applications missing a figure are excluded from that figure's aggregate and counted in
    `incomplete_financials`, so a partly-filled dashboard is visibly partial rather than
    quietly wrong.
    """

    draft: Annotated[int, Field(ge=0)]
    submitted: Annotated[int, Field(ge=0)]
    under_review: Annotated[int, Field(ge=0)]
    shortlisted: Annotated[int, Field(ge=0)]
    approved: Annotated[int, Field(ge=0)]
    rejected: Annotated[int, Field(ge=0)]
    withdrawn: Annotated[int, Field(ge=0)]
    waiting: Annotated[
        int,
        Field(
            ge=0,
            description=(
                "Applications still awaiting a buyer decision: submitted, under review, or "
                "shortlisted."
            ),
        ),
    ]
    total_bid_value: Annotated[
        Decimal, Field(description="Sum of `bid_amount` over approved applications.")
    ]
    total_margin: Annotated[
        Decimal,
        Field(
            description=(
                "Sum of `bid_amount - estimated_cost` over approved applications where both "
                "figures are present. Can be negative."
            )
        ),
    ]
    margin_percentage: Annotated[
        float | None,
        Field(
            description=(
                "`total_margin / total_bid_value` as a fraction — 0.18 means 18%. Null when "
                "the denominator is zero."
            )
        ),
    ]
    win_rate: Annotated[
        float | None,
        Field(
            ge=0,
            le=1,
            description=(
                "approved / (approved + rejected), as a fraction. Null when nothing has been "
                "decided yet — a rate over no decisions is not zero, it is unknown."
            ),
        ),
    ]
    incomplete_financials: Annotated[
        int,
        Field(
            ge=0,
            description=(
                "Approved applications missing a bid amount or an estimated cost, and so "
                "excluded from the money figures above."
            ),
        ),
    ]
