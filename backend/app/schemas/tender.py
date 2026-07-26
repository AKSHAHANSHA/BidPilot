"""Tender and document schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import DocumentExtractionStatus, TenderStatus

MAX_NOTES_LENGTH = 4000


class TenderBase(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=255)]
    buyer: Annotated[str | None, Field(max_length=255)] = None
    reference: Annotated[str | None, Field(max_length=120)] = None
    industry: Annotated[str | None, Field(max_length=120)] = None
    submission_deadline: datetime | None = None
    notes: Annotated[str | None, Field(max_length=MAX_NOTES_LENGTH)] = None

    @field_validator("buyer", "reference", "industry")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("title")
    @classmethod
    def _title_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Title must contain non-whitespace characters")
        return value.strip()

    @field_validator("submission_deadline")
    @classmethod
    def _deadline_is_aware(cls, value: datetime | None) -> datetime | None:
        # A naive deadline cannot be compared against now() for deadline scoring.
        if value is not None and value.tzinfo is None:
            raise ValueError("Submission deadline must include a timezone offset")
        return value


class TenderCreate(TenderBase):
    pass


class TenderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    buyer: Annotated[str | None, Field(max_length=255)] = None
    reference: Annotated[str | None, Field(max_length=120)] = None
    industry: Annotated[str | None, Field(max_length=120)] = None
    submission_deadline: datetime | None = None
    status: TenderStatus | None = None
    notes: Annotated[str | None, Field(max_length=MAX_NOTES_LENGTH)] = None

    @field_validator("submission_deadline")
    @classmethod
    def _deadline_is_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("Submission deadline must include a timezone offset")
        return value


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tender_id: str
    original_filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    page_count: int | None
    extraction_status: DocumentExtractionStatus
    created_at: datetime

    @field_validator("id", "tender_id", mode="before")
    @classmethod
    def _stringify(cls, value: object) -> str:
        return str(value)


class DocumentPageSummary(BaseModel):
    """Per-page metadata without the text — the document's extraction overview."""

    model_config = ConfigDict(from_attributes=True)

    page_number: int
    character_count: int
    quality_score: float
    extraction_method: str


class DocumentPageRead(DocumentPageSummary):
    """One page with its extracted text, for the source viewer."""

    text: str


class TenderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    buyer: str | None
    reference: str | None
    industry: str | None
    submission_deadline: datetime | None
    status: TenderStatus
    notes: str | None
    document_count: int = 0
    created_at: datetime
    updated_at: datetime

    @field_validator("id", mode="before")
    @classmethod
    def _stringify(cls, value: object) -> str:
        return str(value)
