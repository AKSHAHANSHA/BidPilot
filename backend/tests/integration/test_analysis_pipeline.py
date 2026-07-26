"""The pipeline's own behaviour, driven directly against the database.

These exercise the state machine's failure and idempotency paths that are awkward to trigger
through the API, using real rows so the committed transitions are genuine.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import (
    AnalysisErrorCode,
    AnalysisStage,
    AnalysisStatus,
    DocumentExtractionStatus,
)
from app.models.analysis import Analysis
from app.models.document import Document
from app.models.document_page import DocumentPage
from app.models.tender import Tender
from app.workers.pipeline import run_analysis
from tests.integration.factories import make_user, metadata_json, requirement_batch_json

pytestmark = pytest.mark.integration


def _provider() -> object:
    """A schema-routed mock. Phase 6 does not verify quotes (Phase 7 does), and source_page 1
    is valid for these single-page fixtures, so the requirements persist."""
    from app.ai.providers.mock import RoutedMockProvider

    return RoutedMockProvider(
        {
            "tender_metadata": metadata_json(),
            "requirement_batch": requirement_batch_json(12),
        }
    )


async def _tender(session: AsyncSession, user_id: object) -> Tender:
    tender = Tender(owner_user_id=user_id, title="Pipeline test tender")
    session.add(tender)
    await session.flush()
    return tender


async def _document(
    session: AsyncSession,
    *,
    user_id: object,
    tender_id: object,
    status: str = DocumentExtractionStatus.EXTRACTED.value,
    pages: tuple[str, ...] = ("Real contract text " * 6,),
) -> Document:
    document = Document(
        owner_user_id=user_id,
        tender_id=tender_id,
        original_filename="doc.pdf",
        stored_filename="x.pdf",
        storage_key=f"{user_id}/{tender_id}/x.pdf",
        mime_type="application/pdf",
        size_bytes=100,
        sha256="a" * 64,
        page_count=len(pages),
        extraction_status=status,
    )
    session.add(document)
    await session.flush()
    for i, text in enumerate(pages, 1):
        session.add(
            DocumentPage(
                owner_user_id=user_id,
                document_id=document.id,
                page_number=i,
                text=text,
                normalized_text=text,
                character_count=len(text),
                quality_score=0.8 if text.strip() else 0.0,
                extraction_method="native",
            )
        )
    await session.flush()
    return document


async def _analysis(session: AsyncSession, *, user_id: object, tender_id: object, doc_id: object):
    analysis = Analysis(
        owner_user_id=user_id,
        tender_id=tender_id,
        document_id=doc_id,
        version=1,
        status=AnalysisStatus.QUEUED.value,
        current_stage=AnalysisStage.QUEUED.value,
    )
    session.add(analysis)
    await session.commit()
    return analysis


async def test_pipeline_completes_and_records_provenance(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    tender = await _tender(db_session, user.id)
    doc = await _document(db_session, user_id=user.id, tender_id=tender.id)
    analysis = await _analysis(db_session, user_id=user.id, tender_id=tender.id, doc_id=doc.id)

    await run_analysis(db_session, str(analysis.id), provider=_provider())
    await db_session.refresh(analysis)

    assert analysis.status == AnalysisStatus.COMPLETED.value
    assert analysis.current_stage == AnalysisStage.COMPLETED.value
    assert analysis.attempt_count == 1
    assert analysis.started_at is not None
    assert analysis.completed_at >= analysis.started_at
    assert "requirements extracted" in (analysis.summary or "")


async def test_pipeline_fails_validation_without_a_document(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    tender = await _tender(db_session, user.id)
    analysis = await _analysis(db_session, user_id=user.id, tender_id=tender.id, doc_id=None)

    await run_analysis(db_session, str(analysis.id))
    await db_session.refresh(analysis)

    assert analysis.status == AnalysisStatus.FAILED.value
    assert analysis.error_code == AnalysisErrorCode.FAILED_VALIDATION.value
    assert analysis.can_retry is True


async def test_pipeline_rejects_unsupported_document(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    tender = await _tender(db_session, user.id)
    doc = await _document(
        db_session,
        user_id=user.id,
        tender_id=tender.id,
        status=DocumentExtractionStatus.UNSUPPORTED.value,
        pages=("", "", ""),
    )
    analysis = await _analysis(db_session, user_id=user.id, tender_id=tender.id, doc_id=doc.id)

    await run_analysis(db_session, str(analysis.id))
    await db_session.refresh(analysis)

    assert analysis.status == AnalysisStatus.FAILED.value
    assert analysis.error_code == AnalysisErrorCode.FAILED_VALIDATION.value


async def test_pipeline_is_idempotent_on_a_terminal_analysis(db_session: AsyncSession) -> None:
    """A duplicate message delivery must not reprocess a finished job."""
    user = await make_user(db_session)
    tender = await _tender(db_session, user.id)
    doc = await _document(db_session, user_id=user.id, tender_id=tender.id)
    analysis = await _analysis(db_session, user_id=user.id, tender_id=tender.id, doc_id=doc.id)

    await run_analysis(db_session, str(analysis.id), provider=_provider())
    await db_session.refresh(analysis)
    first_completed = analysis.completed_at
    first_attempts = analysis.attempt_count

    # Re-deliver the same message.
    await run_analysis(db_session, str(analysis.id))
    await db_session.refresh(analysis)
    assert analysis.completed_at == first_completed
    assert analysis.attempt_count == first_attempts  # not reprocessed


async def test_pipeline_ignores_a_missing_analysis(db_session: AsyncSession) -> None:
    import uuid

    # Must not raise — a message for a deleted analysis is a no-op.
    await run_analysis(db_session, str(uuid.uuid4()))
