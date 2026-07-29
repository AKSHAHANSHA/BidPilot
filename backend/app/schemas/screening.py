"""Document-screening read schemas.

Every field here is an *output*: screening is produced by the pipeline, never submitted by a
client, so there is no write shape in this module.

Two rules from `docs/09_PORTAL_SPEC.md` shape what these carry. §8: the score is computed in
Python from the findings, so `overall_score` is null until the run completes and is never
sent by the model. §7 and `CLAUDE.md`: a page that could not be read is reported as
`present_unreadable` and counted in `pages_needing_ocr`, never folded into `missing` —
"not found" is not proof of non-existence, and the two need different actions from the vendor.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.domain.enums import (
    AnalysisErrorCode,
    DocumentScreeningVerdict,
    RequiredDocumentType,
    ScreeningStatus,
)
from app.schemas.listing import label_for


class FindingRead(BaseModel):
    """One requirement's verdict with the evidence behind it.

    There is exactly one finding per checklist entry, including the ones nothing satisfied —
    the absence *is* the finding. No separate `id` is exposed: `document_type` is unique
    within a screening (the database says so), which makes it the natural key for the UI.
    """

    model_config = ConfigDict(from_attributes=True)

    document_type: RequiredDocumentType
    verdict: DocumentScreeningVerdict
    is_mandatory: Annotated[
        bool,
        Field(
            description=(
                "Copied from the requirement when the screening ran, so a later edit to the "
                "checklist cannot change what this result was measured against."
            )
        ),
    ]
    weight: int
    matched_document_id: Annotated[
        uuid.UUID | None,
        Field(
            description=(
                "The upload that satisfied this requirement. Always present for a `present` or "
                "`present_expired` verdict — a match with nothing behind it is not a match."
            )
        ),
    ]
    source_page: Annotated[
        int | None, Field(ge=1, description="1-based page the evidence quote was verified on.")
    ]
    evidence_quote: Annotated[
        str | None,
        Field(
            description=(
                "Verbatim text from the matched page, re-checked against the stored page text "
                "before this finding was written."
            )
        ),
    ]
    note: Annotated[
        str | None,
        Field(description='Reviewer-facing explanation, e.g. "licence expires before closing".'),
    ]
    confidence: Annotated[
        float | None,
        Field(
            ge=0,
            le=1,
            description=(
                "The classifier's self-reported confidence. Advisory only — it never scales "
                "the score."
            ),
        ),
    ]

    @computed_field(description="Human-readable form of `document_type`.")  # type: ignore[prop-decorator]
    @property
    def label(self) -> str:
        return label_for(self.document_type)


class ScreeningSummary(BaseModel):
    """The compact form embedded in an applicant row or a vendor's application.

    Enough to rank and to spot a blocking gap; the findings themselves come from
    `GET /applications/{id}/screening`.
    """

    model_config = ConfigDict(from_attributes=True)

    status: ScreeningStatus
    overall_score: Annotated[
        int | None,
        Field(ge=0, le=100, description="Null until the run completes. Computed in Python."),
    ]
    mandatory_met: int
    mandatory_total: int
    has_blocking_gap: Annotated[
        bool,
        Field(
            description=(
                "True when a mandatory requirement is unmet. The score is still shown: a buyer "
                "is entitled to see that an otherwise strong bid is missing one certificate."
            )
        ),
    ]
    completed_at: datetime | None


class ScreeningRead(BaseModel):
    """The vendor's full screening result, polled while `pending` or `processing`.

    There is no progress percentage: the status is the real pipeline state, and a fabricated
    number would be a lie the vendor cannot check (`CLAUDE.md`).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    status: ScreeningStatus
    overall_score: Annotated[
        int | None,
        Field(
            ge=0,
            le=100,
            description=(
                "0-100, computed in Python from the findings below. Null until the run "
                "completes — a partial score would read as a real result."
            ),
        ),
    ]
    mandatory_met: int
    mandatory_total: int
    optional_met: int
    optional_total: int
    documents_processed: int
    pages_extracted: int
    pages_needing_ocr: Annotated[
        int,
        Field(
            description=(
                "Pages with no readable text layer that OCR could not recover. Reported as "
                '"could not be read", never as a missing document.'
            )
        ),
    ]
    summary: Annotated[
        str | None,
        Field(
            description=(
                "Advisory narrative generated from the validated findings, never from raw "
                "document text."
            )
        ),
    ]
    scoring_version: Annotated[
        str, Field(description="Which scoring rules produced this result, for reproducibility.")
    ]
    has_blocking_gap: bool
    error_code: Annotated[
        AnalysisErrorCode | None,
        Field(description="Safe, machine-readable failure reason. Detail stays in the logs."),
    ]
    started_at: datetime | None
    completed_at: datetime | None
    findings: list[FindingRead]
