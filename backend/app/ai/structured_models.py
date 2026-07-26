"""Strict schemas the provider must return.

These are the contract between the model and the pipeline. Unknown enums, missing fields, and
extra keys are rejected here (`extra="forbid"`), so a malformed completion can never become a
persisted finding (`docs/03` §5). `model_json_schema()` is handed to the provider as its
required output shape; the raw response is validated back through the same model.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import RequirementCategory, RequirementObligation


class ExtractedRequirement(BaseModel):
    """One requirement as the model reports it, before citation verification."""

    model_config = ConfigDict(extra="forbid")

    original_text: Annotated[str, Field(min_length=1, max_length=4000)]
    normalized_text: Annotated[str, Field(min_length=1, max_length=2000)]
    category: RequirementCategory
    obligation: RequirementObligation
    expected_evidence: Annotated[list[Annotated[str, Field(max_length=200)]], Field(max_length=20)]
    source_page: Annotated[int, Field(ge=1)]
    source_quote: Annotated[str, Field(min_length=1, max_length=2000)]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]


class RequirementBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirements: Annotated[list[ExtractedRequirement], Field(max_length=100)]


class ExtractedMetadata(BaseModel):
    """Tender-level metadata. All fields optional — a tender may not state every one, and
    'not found' must never be fabricated (`docs/03` §10)."""

    model_config = ConfigDict(extra="forbid")

    buyer: Annotated[str | None, Field(max_length=255)] = None
    reference: Annotated[str | None, Field(max_length=120)] = None
    submission_deadline_text: Annotated[str | None, Field(max_length=120)] = None
    contract_duration: Annotated[str | None, Field(max_length=120)] = None
    estimated_value: Annotated[str | None, Field(max_length=120)] = None
    currency: Annotated[str | None, Field(max_length=8)] = None
    summary: Annotated[str | None, Field(max_length=2000)] = None
