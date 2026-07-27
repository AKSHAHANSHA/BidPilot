"""Risk finding read and review schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import (
    CitationMatchMethod,
    ComplianceStatus,
    RiskSeverity,
    RiskType,
)


class RiskCitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    page_number: int
    source_quote: str
    verified: bool
    match_method: CitationMatchMethod
    match_score: float | None

    @field_validator("id", "document_id", mode="before")
    @classmethod
    def _stringify(cls, value: object) -> str:
        return str(value)


class RiskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    analysis_id: str
    risk_type: RiskType
    severity: RiskSeverity
    summary: str
    why_it_matters: str
    suggested_action: str
    confidence: float
    citation_verified: bool
    reviewed_status: ComplianceStatus
    review_reason: str | None
    citations: list[RiskCitationRead]
    created_at: datetime

    @field_validator("id", "analysis_id", mode="before")
    @classmethod
    def _stringify(cls, value: object) -> str:
        return str(value)


class ReviewRequest(BaseModel):
    """A human override of a machine verdict.

    A reason is mandatory (`docs/03` §11 / CLAUDE.md): an override must be justified and the
    original machine result is preserved (`machine_status` is never touched by review).
    """

    reviewed_status: ComplianceStatus
    reason: Annotated[str, Field(min_length=3, max_length=2000)]

    @field_validator("reason")
    @classmethod
    def _reason_is_substantive(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 3:
            raise ValueError("A review reason is required.")
        return stripped
