"""Requirement and citation read schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.domain.enums import (
    CitationMatchMethod,
    ComplianceStatus,
    RequirementCategory,
    RequirementObligation,
)


class CitationRead(BaseModel):
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


class RequirementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    analysis_id: str
    category: RequirementCategory
    obligation: RequirementObligation
    original_text: str
    normalized_text: str
    expected_evidence: list[str]
    confidence: float
    citation_verified: bool
    machine_status: ComplianceStatus
    reviewed_status: ComplianceStatus
    review_reason: str | None
    citations: list[CitationRead]
    created_at: datetime

    @field_validator("id", "analysis_id", mode="before")
    @classmethod
    def _stringify(cls, value: object) -> str:
        return str(value)
