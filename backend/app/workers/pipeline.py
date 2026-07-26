"""The analysis pipeline: an ordered list of stage handlers over one session.

Structured as a registry so each roadmap phase adds its stage without touching the
orchestration. Phase 5 implements the stages that exist today (validate the document, confirm
extraction, assess quality); phases 6-9 insert metadata, requirements, citations, matching,
risks, scoring, and report generation ahead of `completed`.

Every stage transition is committed immediately, so status in PostgreSQL always reflects real
progress and a crash leaves an accurate `current_stage` rather than a lie.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.cost import estimate_cost
from app.ai.extraction import (
    ExtractionError,
    TokenUsage,
    extract_metadata,
    extract_requirements,
)
from app.ai.providers.base import LLMProvider, LLMProviderError
from app.core.logging import get_logger, user_id_var
from app.documents.extraction import MIN_TEXTUAL_PAGE_RATIO
from app.domain.enums import (
    AnalysisErrorCode,
    AnalysisStage,
    AnalysisStatus,
    ComplianceStatus,
    DocumentExtractionStatus,
)
from app.models.analysis import Analysis
from app.models.document import Document
from app.models.document_page import DocumentPage
from app.models.requirement import Requirement, RequirementCitation
from app.models.tender_metadata import TenderMetadata

logger = get_logger(__name__)


class StageError(Exception):
    """A stage failed in a way that maps to a specific analysis error code."""

    def __init__(self, error_code: AnalysisErrorCode, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message


@dataclass
class PipelineContext:
    """Mutable state threaded through the stages of one run."""

    session: AsyncSession
    analysis: Analysis
    provider: LLMProvider | None = None
    document: Document | None = None
    pages: list[DocumentPage] | None = None
    usage: TokenUsage = field(default_factory=TokenUsage)


StageHandler = Callable[[PipelineContext], Awaitable[None]]


async def _advance(ctx: PipelineContext, stage: AnalysisStage, message: str) -> None:
    """Record a stage transition and commit it, so external readers see live progress."""
    ctx.analysis.current_stage = stage.value
    ctx.analysis.stage_message = message
    await ctx.session.commit()
    logger.info(
        "analysis_stage",
        extra={"analysis_id": str(ctx.analysis.id), "stage": stage.value},
    )


# --- Stage handlers ------------------------------------------------------------------------


async def stage_validating(ctx: PipelineContext) -> None:
    await _advance(ctx, AnalysisStage.VALIDATING, "Checking the uploaded document.")
    if ctx.analysis.document_id is None:
        raise StageError(
            AnalysisErrorCode.FAILED_VALIDATION,
            "No document is attached to this tender.",
        )
    document = await ctx.session.get(Document, ctx.analysis.document_id)
    if document is None or document.owner_user_id != ctx.analysis.owner_user_id:
        raise StageError(AnalysisErrorCode.FAILED_VALIDATION, "The document could not be found.")
    if document.extraction_status == DocumentExtractionStatus.UNSUPPORTED.value:
        raise StageError(
            AnalysisErrorCode.FAILED_VALIDATION,
            "The document has no readable text (it appears to be scanned). OCR is not available.",
        )
    ctx.document = document


async def stage_extracting_text(ctx: PipelineContext) -> None:
    await _advance(ctx, AnalysisStage.EXTRACTING_TEXT, "Loading page-aware text.")
    assert ctx.document is not None  # noqa: S101 - guaranteed by the validating stage
    result = await ctx.session.execute(
        select(DocumentPage)
        .where(DocumentPage.document_id == ctx.document.id)
        .order_by(DocumentPage.page_number)
    )
    pages = list(result.scalars().all())
    if not pages:
        raise StageError(
            AnalysisErrorCode.FAILED_EXTRACTION, "The document has no extracted pages."
        )
    ctx.pages = pages


async def stage_assessing_quality(ctx: PipelineContext) -> None:
    await _advance(ctx, AnalysisStage.ASSESSING_QUALITY, "Assessing extraction quality.")
    assert ctx.pages is not None  # noqa: S101
    textual = [p for p in ctx.pages if p.quality_score > 0]
    ratio = len(textual) / len(ctx.pages)
    if ratio < MIN_TEXTUAL_PAGE_RATIO:
        raise StageError(
            AnalysisErrorCode.FAILED_EXTRACTION,
            "Too little of the document contains readable text to analyse.",
        )
    total_chars = sum(p.character_count for p in ctx.pages)
    ctx.analysis.summary = (
        f"{len(ctx.pages)} pages, {len(textual)} with readable text, "
        f"{total_chars:,} characters extracted."
    )


def _require_provider(ctx: PipelineContext) -> LLMProvider:
    if ctx.provider is None:
        # A run reached an AI stage without a configured provider — a deployment/config fault.
        raise StageError(
            AnalysisErrorCode.FAILED_INTERNAL,
            "AI extraction is not configured on this deployment.",
        )
    return ctx.provider


async def stage_extracting_metadata(ctx: PipelineContext) -> None:
    await _advance(ctx, AnalysisStage.EXTRACTING_METADATA, "Extracting tender metadata.")
    provider = _require_provider(ctx)
    assert ctx.pages is not None  # noqa: S101
    try:
        result = await extract_metadata(provider, ctx.pages)
    except LLMProviderError as exc:
        raise StageError(AnalysisErrorCode.FAILED_AI, str(exc)) from exc
    ctx.usage.add(result.input_tokens, result.output_tokens)

    md = result.metadata
    ctx.session.add(
        TenderMetadata(
            owner_user_id=ctx.analysis.owner_user_id,
            analysis_id=ctx.analysis.id,
            buyer=md.buyer,
            reference=md.reference,
            submission_deadline_text=md.submission_deadline_text,
            contract_duration=md.contract_duration,
            estimated_value=md.estimated_value,
            currency=md.currency,
            summary=md.summary,
        )
    )


async def stage_extracting_requirements(ctx: PipelineContext) -> None:
    await _advance(
        ctx, AnalysisStage.EXTRACTING_REQUIREMENTS, "Extracting requirements from the tender."
    )
    provider = _require_provider(ctx)
    assert ctx.pages is not None and ctx.document is not None  # noqa: S101
    try:
        result = await extract_requirements(provider, ctx.pages)
    except ExtractionError as exc:
        raise StageError(AnalysisErrorCode.FAILED_AI, str(exc)) from exc
    except LLMProviderError as exc:
        raise StageError(AnalysisErrorCode.FAILED_AI, str(exc)) from exc
    ctx.usage.add(result.usage.input_tokens, result.usage.output_tokens)

    for extracted in result.requirements:
        requirement = Requirement(
            owner_user_id=ctx.analysis.owner_user_id,
            analysis_id=ctx.analysis.id,
            category=extracted.category.value,
            obligation=extracted.obligation.value,
            original_text=extracted.original_text,
            normalized_text=extracted.normalized_text,
            expected_evidence=list(extracted.expected_evidence),
            confidence=extracted.confidence,
            # Not canonical until Phase 7 verifies the quote against the page.
            citation_verified=False,
            machine_status=ComplianceStatus.UNREVIEWED.value,
            reviewed_status=ComplianceStatus.UNREVIEWED.value,
        )
        ctx.session.add(requirement)
        await ctx.session.flush()  # populate requirement.id for the citation FK
        ctx.session.add(
            RequirementCitation(
                owner_user_id=ctx.analysis.owner_user_id,
                requirement_id=requirement.id,
                document_id=ctx.document.id,
                page_number=extracted.source_page,
                source_quote=extracted.source_quote,
            )
        )

    ctx.analysis.summary = (
        f"{len(result.requirements)} requirements extracted from "
        f"{ctx.document.page_count or len(ctx.pages)} pages. "
        "Citations are verified in the next stage."
    )


#: Ordered pipeline. Phases 7-9 insert citation verification, matching, risks, scoring, and
#: report generation between requirement extraction and COMPLETED.
PIPELINE: tuple[tuple[AnalysisStage, StageHandler], ...] = (
    (AnalysisStage.VALIDATING, stage_validating),
    (AnalysisStage.EXTRACTING_TEXT, stage_extracting_text),
    (AnalysisStage.ASSESSING_QUALITY, stage_assessing_quality),
    (AnalysisStage.EXTRACTING_METADATA, stage_extracting_metadata),
    (AnalysisStage.EXTRACTING_REQUIREMENTS, stage_extracting_requirements),
)


async def _reset_findings(session: AsyncSession, analysis_id: uuid.UUID) -> None:
    """Delete an analysis's derived records so a re-run starts clean."""
    from sqlalchemy import delete

    await session.execute(delete(Requirement).where(Requirement.analysis_id == analysis_id))
    await session.execute(delete(TenderMetadata).where(TenderMetadata.analysis_id == analysis_id))


async def run_analysis(
    session: AsyncSession, analysis_id: str, *, provider: LLMProvider | None = None
) -> None:
    """Execute the pipeline for one analysis. Idempotent-safe and self-contained.

    Owns its transaction boundary because it runs in a worker, detached from any request. On
    failure it records a safe error code and commits, so the failure is durable and the API can
    offer a retry. `provider` is injected so tests supply a mock; the worker builds a real one.
    """
    analysis = await session.get(Analysis, analysis_id)
    if analysis is None:
        logger.warning("analysis_missing", extra={"analysis_id": analysis_id})
        return
    if analysis.is_terminal:
        # A duplicate delivery of the same message must not reprocess a finished job.
        logger.info(
            "analysis_already_terminal",
            extra={"analysis_id": analysis_id, "status": analysis.status},
        )
        return

    # Bind the owner to the logging context so worker logs are attributable, exactly as the
    # request middleware does for API logs.
    user_id_var.set(str(analysis.owner_user_id))

    analysis.status = AnalysisStatus.PROCESSING.value
    analysis.started_at = datetime.now(tz=UTC)
    analysis.attempt_count += 1
    analysis.error_code = None
    # A re-run replaces its own derived records. Clearing them first makes retry idempotent —
    # otherwise re-inserting a requirement or the one-per-analysis metadata row would violate a
    # unique constraint and fail the run for the wrong reason.
    await _reset_findings(session, analysis.id)
    await session.commit()

    ctx = PipelineContext(session=session, analysis=analysis, provider=provider)
    try:
        for _stage, handler in PIPELINE:
            await handler(ctx)
    except StageError as exc:
        await session.rollback()
        analysis.status = AnalysisStatus.FAILED.value
        analysis.error_code = exc.error_code.value
        analysis.stage_message = exc.message
        analysis.completed_at = datetime.now(tz=UTC)
        await session.commit()
        logger.warning(
            "analysis_failed",
            extra={"analysis_id": analysis_id, "error_code": exc.error_code.value},
        )
        return
    except Exception:
        await session.rollback()
        analysis.status = AnalysisStatus.FAILED.value
        analysis.error_code = AnalysisErrorCode.FAILED_INTERNAL.value
        analysis.stage_message = "An unexpected error occurred during analysis."
        analysis.completed_at = datetime.now(tz=UTC)
        await session.commit()
        logger.exception("analysis_error", extra={"analysis_id": analysis_id})
        return

    # Record token usage, estimated cost, and provenance from what the run actually consumed.
    analysis.input_tokens = ctx.usage.input_tokens
    analysis.output_tokens = ctx.usage.output_tokens
    if ctx.provider is not None and ctx.usage.calls:
        analysis.provider = getattr(ctx.provider, "provider_name", "openai")
        analysis.model = getattr(ctx.provider, "model", None)
        analysis.estimated_cost = estimate_cost(
            model=analysis.model or "",
            input_tokens=ctx.usage.input_tokens,
            output_tokens=ctx.usage.output_tokens,
        )
    analysis.status = AnalysisStatus.COMPLETED.value
    analysis.current_stage = AnalysisStage.COMPLETED.value
    analysis.stage_message = "Analysis complete."
    analysis.completed_at = datetime.now(tz=UTC)
    await session.commit()
    logger.info(
        "analysis_completed",
        extra={
            "analysis_id": analysis_id,
            "input_tokens": ctx.usage.input_tokens,
            "output_tokens": ctx.usage.output_tokens,
        },
    )
