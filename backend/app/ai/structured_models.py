"""Strict schemas the provider must return.

These are the contract between the model and the pipeline. Unknown enums, missing fields, and
extra keys are rejected here (`extra="forbid"`), so a malformed completion can never become a
persisted finding (`docs/03` §5). `model_json_schema()` is handed to the provider as its
required output shape; the raw response is validated back through the same model.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import (
    Emirate,
    RequirementCategory,
    RequirementObligation,
    RiskSeverity,
    RiskType,
    TenderCategory,
)


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


class ExtractedRisk(BaseModel):
    """One risk clause as the model reports it, before citation verification."""

    model_config = ConfigDict(extra="forbid")

    risk_type: RiskType
    severity: RiskSeverity
    summary: Annotated[str, Field(min_length=1, max_length=1000)]
    why_it_matters: Annotated[str, Field(min_length=1, max_length=1000)]
    suggested_action: Annotated[str, Field(min_length=1, max_length=1000)]
    source_page: Annotated[int, Field(ge=1)]
    source_quote: Annotated[str, Field(min_length=1, max_length=2000)]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]


class RiskBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risks: Annotated[list[ExtractedRisk], Field(max_length=50)]


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


class SearchInterpretation(BaseModel):
    """What a free-text search query was understood to ask for (`docs/09` §5).

    The model maps a sentence onto our controlled vocabularies and nothing more: it never sees
    the listing set, so it cannot invent, order, or describe a listing. Ranking is deterministic
    Python over these fields.

    Every field is bounded. The keyword provider's output is small by construction, but a real
    completion is attacker-influenced text (the query is public and unauthenticated), and an
    unbounded list or string is a denial-of-service vector on whatever ranks it afterwards.

    Every field also defaults to empty: a query that maps to nothing is a legitimate answer
    ("show me everything"), not a validation failure.
    """

    model_config = ConfigDict(extra="forbid")

    categories: Annotated[list[TenderCategory], Field(max_length=6)] = []
    emirates: Annotated[list[Emirate], Field(max_length=7)] = []
    keywords: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=40)]], Field(max_length=10)
    ] = []
    #: An approximate band in AED, not a hard filter, so `float` is honest about the precision
    #: on offer. The ranker converts to `Decimal` before comparing with `tender_listings.budget_*`.
    budget_min: Annotated[float | None, Field(ge=0, le=1e12)] = None
    budget_max: Annotated[float | None, Field(ge=0, le=1e12)] = None
    #: One sentence echoed to the UI so the visitor can see what was understood and correct it.
    interpretation: Annotated[str, Field(max_length=280)] = ""
