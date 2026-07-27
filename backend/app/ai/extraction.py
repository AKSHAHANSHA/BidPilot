"""Extraction orchestration: batch pages, call the provider, validate, accumulate cost.

This is where provider output becomes trustworthy. The raw JSON is validated against a strict
model in our code, so a malformed response or an unknown enum raises here and never reaches the
database. A schema-validation failure is retried once; a persistent failure is surfaced as an
AI error the pipeline records against the analysis.

Batching keeps each request within a sane token window (`docs/03` §4): pages are grouped so a
batch is roughly a few thousand characters, and page boundaries are preserved so the model can
cite a real page number.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import ValidationError

from app.ai.cost import estimate_cost
from app.ai.prompts import METADATA_PROMPT, REQUIREMENTS_PROMPT, RISKS_PROMPT
from app.ai.providers.base import LLMProvider, LLMProviderError
from app.ai.structured_models import (
    ExtractedMetadata,
    ExtractedRequirement,
    ExtractedRisk,
    RequirementBatch,
    RiskBatch,
)
from app.core.logging import get_logger
from app.models.document_page import DocumentPage

logger = get_logger(__name__)

#: Target characters per extraction batch. A page group near this size stays well inside the
#: model's context while keeping enough surrounding text for the model to judge obligations.
BATCH_TARGET_CHARS = 6000


class ExtractionError(LLMProviderError):
    """Extraction failed after validation retries; mapped to a FAILED_AI analysis error."""


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0

    def add(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.calls += 1


@dataclass
class RequirementExtractionResult:
    requirements: list[ExtractedRequirement] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=TokenUsage)


def batch_pages(pages: list[DocumentPage]) -> list[list[DocumentPage]]:
    """Group consecutive text-bearing pages into batches near `BATCH_TARGET_CHARS`.

    Textless pages are skipped — they carry nothing to extract — but numbering is preserved
    because each page keeps its own `page_number`.
    """
    batches: list[list[DocumentPage]] = []
    current: list[DocumentPage] = []
    size = 0
    for page in pages:
        if page.character_count == 0:
            continue
        if current and size + page.character_count > BATCH_TARGET_CHARS:
            batches.append(current)
            current = []
            size = 0
        current.append(page)
        size += page.character_count
    if current:
        batches.append(current)
    return batches


def _render_batch(pages: list[DocumentPage]) -> str:
    """Render a batch as page-labelled text so quotes map to real page numbers."""
    return "\n\n".join(f"[page {p.page_number}]\n{p.text}" for p in pages)


def _valid_pages(pages: list[DocumentPage]) -> set[int]:
    return {p.page_number for p in pages}


async def extract_requirements(
    provider: LLMProvider, pages: list[DocumentPage]
) -> RequirementExtractionResult:
    """Extract requirements across all batches, validating each response strictly."""
    result = RequirementExtractionResult()
    for batch in batch_pages(pages):
        allowed = _valid_pages(batch)
        parsed = await _extract_batch(provider, batch)
        result.usage.add(parsed.input_tokens, parsed.output_tokens)
        for requirement in parsed.batch.requirements:
            # A page the model names must be one we actually sent; a hallucinated page number is
            # dropped here, before Phase 7's quote verification even runs.
            if requirement.source_page not in allowed:
                logger.warning(
                    "requirement_dropped_bad_page",
                    extra={"claimed_page": requirement.source_page},
                )
                continue
            result.requirements.append(requirement)
    return result


@dataclass
class _ParsedBatch:
    batch: RequirementBatch
    input_tokens: int
    output_tokens: int


async def _extract_batch(provider: LLMProvider, pages: list[DocumentPage]) -> _ParsedBatch:
    user = REQUIREMENTS_PROMPT.render_user(document_text=_render_batch(pages))
    schema = RequirementBatch.model_json_schema()

    last_error: Exception | None = None
    for attempt in range(2):  # one validation retry
        response = await provider.complete_json(
            system=REQUIREMENTS_PROMPT.system,
            user=user,
            schema=schema,
            schema_name="requirement_batch",
        )
        try:
            batch = RequirementBatch.model_validate_json(response.content)
            return _ParsedBatch(batch, response.input_tokens, response.output_tokens)
        except ValidationError as exc:
            last_error = exc
            logger.warning("requirement_batch_invalid", extra={"attempt": attempt})

    raise ExtractionError(
        f"The AI returned output that did not match the required schema: {last_error}"
    )


@dataclass
class RiskExtractionResult:
    risks: list[ExtractedRisk] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=TokenUsage)


async def extract_risks(provider: LLMProvider, pages: list[DocumentPage]) -> RiskExtractionResult:
    """Extract risk clauses across batches, validating each response and dropping bad pages."""
    result = RiskExtractionResult()
    for batch in batch_pages(pages):
        allowed = _valid_pages(batch)
        user = RISKS_PROMPT.render_user(document_text=_render_batch(batch))
        schema = RiskBatch.model_json_schema()

        parsed: RiskBatch | None = None
        last_error: Exception | None = None
        for _attempt in range(2):
            response = await provider.complete_json(
                system=RISKS_PROMPT.system,
                user=user,
                schema=schema,
                schema_name="risk_batch",
            )
            result.usage.add(response.input_tokens, response.output_tokens)
            try:
                parsed = RiskBatch.model_validate_json(response.content)
                break
            except ValidationError as exc:
                last_error = exc
                logger.warning("risk_batch_invalid")
        if parsed is None:
            raise ExtractionError(f"The AI returned invalid risk output: {last_error}")

        for risk in parsed.risks:
            if risk.source_page not in allowed:
                logger.warning("risk_dropped_bad_page", extra={"claimed_page": risk.source_page})
                continue
            result.risks.append(risk)
    return result


@dataclass
class MetadataExtractionResult:
    metadata: ExtractedMetadata
    input_tokens: int
    output_tokens: int


async def extract_metadata(
    provider: LLMProvider, pages: list[DocumentPage]
) -> MetadataExtractionResult:
    """Extract tender metadata from the opening pages, where it almost always appears."""
    head = [p for p in pages if p.character_count > 0][:4]
    user = METADATA_PROMPT.render_user(document_text=_render_batch(head))
    response = await provider.complete_json(
        system=METADATA_PROMPT.system,
        user=user,
        schema=ExtractedMetadata.model_json_schema(),
        schema_name="tender_metadata",
    )
    try:
        metadata = ExtractedMetadata.model_validate_json(response.content)
    except ValidationError as exc:
        raise ExtractionError(f"The AI returned invalid metadata: {exc}") from exc
    return MetadataExtractionResult(metadata, response.input_tokens, response.output_tokens)


def total_cost(model: str, usage: TokenUsage) -> object:
    return estimate_cost(
        model=model, input_tokens=usage.input_tokens, output_tokens=usage.output_tokens
    )
