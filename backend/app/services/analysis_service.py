"""Analysis orchestration: create, enqueue, retry, and query runs.

Idempotency (`docs/02` §6): a new analysis while one is still queued or processing returns the
existing run rather than starting a duplicate; otherwise it creates the next version. Retry
re-runs a failed run in place, incrementing its attempt count.

The service commits the analysis row before enqueuing, so a Dramatiq worker in a separate
transaction is guaranteed to see it.
"""

from __future__ import annotations

import uuid

from app.api.errors import ConflictError, NotFoundError, ValidationProblem
from app.core.config import Settings
from app.core.logging import get_logger
from app.domain.enums import AnalysisStage, AnalysisStatus, DocumentExtractionStatus
from app.models.analysis import Analysis
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.tender_repository import DocumentRepository, TenderRepository
from app.workers.queue import JobQueue

logger = get_logger(__name__)


class AnalysisService:
    def __init__(
        self,
        *,
        analyses: AnalysisRepository,
        tenders: TenderRepository,
        documents: DocumentRepository,
        job_queue: JobQueue,
        settings: Settings,
    ) -> None:
        self.analyses = analyses
        self.tenders = tenders
        self.documents = documents
        self.job_queue = job_queue
        self.settings = settings

    async def create_analysis(
        self, *, user_id: uuid.UUID, tender_id: uuid.UUID
    ) -> tuple[Analysis, bool]:
        """Queue an analysis of the tender's most recent document.

        Returns (analysis, created). `created=False` means an active run already existed and is
        returned unchanged — enqueuing a second would duplicate work.
        """
        tender = await self.tenders.get_for_user(tender_id, user_id)
        if tender is None:
            raise NotFoundError("Tender not found.")

        existing = await self.analyses.active_for_tender(tender_id, user_id)
        if existing is not None:
            return existing, False

        documents = await self.documents.list_for_tender(tender_id, user_id)
        if not documents:
            raise ValidationProblem("Upload a document to this tender before running an analysis.")
        # Most recent upload first (list is created_at desc).
        document = documents[0]
        if document.extraction_status == DocumentExtractionStatus.UNSUPPORTED.value:
            raise ValidationProblem(
                "The most recent document has no readable text and cannot be analysed."
            )

        version = await self.analyses.next_version(tender_id, user_id)
        analysis = Analysis(
            owner_user_id=user_id,
            tender_id=tender_id,
            document_id=document.id,
            version=version,
            status=AnalysisStatus.QUEUED.value,
            current_stage=AnalysisStage.QUEUED.value,
            stage_message="Queued for analysis.",
            prompt_version=self.settings.prompt_version,
            scoring_version=self.settings.scoring_version,
        )
        self.analyses.add(analysis)
        # Commit before enqueuing: the worker's transaction must be able to see this row.
        await self.analyses.session.commit()

        await self.job_queue.enqueue_analysis(analysis.id)
        logger.info(
            "analysis_queued",
            extra={"analysis_id": str(analysis.id), "tender_id": str(tender_id)},
        )
        # The eager queue (tests/offline demo) has already run and committed the pipeline, so
        # refresh to return the final state; under Dramatiq this is a no-op re-read of "queued".
        await self.analyses.session.refresh(analysis)
        return analysis, True

    async def get_analysis(self, *, user_id: uuid.UUID, analysis_id: uuid.UUID) -> Analysis:
        analysis = await self.analyses.get_for_user(analysis_id, user_id)
        if analysis is None:
            raise NotFoundError("Analysis not found.")
        return analysis

    async def list_for_tender(self, *, user_id: uuid.UUID, tender_id: uuid.UUID) -> list[Analysis]:
        tender = await self.tenders.get_for_user(tender_id, user_id)
        if tender is None:
            raise NotFoundError("Tender not found.")
        return await self.analyses.list_for_tender(tender_id, user_id)

    async def retry_analysis(self, *, user_id: uuid.UUID, analysis_id: uuid.UUID) -> Analysis:
        analysis = await self.get_analysis(user_id=user_id, analysis_id=analysis_id)
        if not analysis.can_retry:
            raise ConflictError(
                f"Only a failed analysis can be retried; this one is {analysis.status}."
            )
        analysis.status = AnalysisStatus.QUEUED.value
        analysis.current_stage = AnalysisStage.QUEUED.value
        analysis.stage_message = "Re-queued for analysis."
        analysis.error_code = None
        analysis.completed_at = None
        await self.analyses.session.commit()

        await self.job_queue.enqueue_analysis(analysis.id)
        logger.info("analysis_retry_queued", extra={"analysis_id": str(analysis.id)})
        await self.analyses.session.refresh(analysis)
        return analysis
