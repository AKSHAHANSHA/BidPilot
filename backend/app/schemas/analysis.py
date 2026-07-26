"""Analysis request and response schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator

from app.domain.enums import AnalysisErrorCode, AnalysisStage, AnalysisStatus


class AnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tender_id: str
    document_id: str | None
    version: int
    status: AnalysisStatus
    current_stage: AnalysisStage
    stage_message: str | None
    attempt_count: int
    error_code: AnalysisErrorCode | None
    started_at: datetime | None
    completed_at: datetime | None
    provider: str | None
    model: str | None
    prompt_version: str | None
    input_tokens: int
    output_tokens: int
    estimated_cost: Decimal
    summary: str | None
    can_retry: bool = False
    created_at: datetime
    updated_at: datetime

    @field_validator("id", "tender_id", "document_id", mode="before")
    @classmethod
    def _stringify(cls, value: object) -> str | None:
        return None if value is None else str(value)


class AnalysisEvent(BaseModel):
    """Compact progress payload for polling — no fabricated percentages (`docs/05`)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    status: AnalysisStatus
    current_stage: AnalysisStage
    stage_message: str | None
    error_code: AnalysisErrorCode | None
    can_retry: bool = False

    @field_validator("id", mode="before")
    @classmethod
    def _stringify(cls, value: object) -> str:
        return str(value)
