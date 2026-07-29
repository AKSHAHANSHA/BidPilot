"""Screening reads for both sides of the marketplace, and the worker's single write path.

Reading and writing here are separated by *who asks*, not by convenience:

* a vendor reaches their screening through their own application (`ApplicationRepository`
  scopes on `vendor_user_id`);
* a buyer reaches it through the listing they own (the same repository joins `tender_listings`
  and filters `owner_user_id` there);
* the worker has no user at all and reaches it by screening ID, which is why
  :meth:`ScreeningService.persist_result` takes an already-loaded row and never looks one up
  from a request.

Two separate read methods rather than one method with a role flag: the flag would be a
parameter a route could get wrong, and the two paths do genuinely different SQL.

**This service does not run the pipeline.** It takes the values the pipeline has already
computed — verdicts scored by `app/domain/screening.py`, evidence verified by
`app/domain/citation.py` — and makes them durable. The score arrives here finished; nothing in
this module computes one, and nothing in it reads document text.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import inspect

from app.api.errors import NotFoundError
from app.core.logging import get_logger
from app.domain.enums import AnalysisErrorCode, RequiredDocumentType, ScreeningStatus
from app.domain.screening import (
    MET_VERDICTS,
    SCREENING_SCORING_VERSION,
    ScreeningResult,
)
from app.models.application import Application
from app.models.listing import TenderListing
from app.models.screening import ApplicationScreening, ScreeningFinding
from app.repositories.application_repository import (
    ApplicationRepository,
    ApplicationScreeningRepository,
)
from app.services.notification_service import NOT_PROOF_OF_ABSENCE, NotificationService

logger = get_logger(__name__)

#: `screening_findings.confidence` is `Numeric(3, 2)` with a `BETWEEN 0 AND 1` constraint.
_CONFIDENCE_QUANTUM = Decimal("0.01")

NOT_SCREENED_DETAIL = (
    "This application has not been screened yet. Screening starts when the application is "
    "submitted."
)


@dataclass(frozen=True, slots=True)
class FindingEvidence:
    """What the pipeline verified for one checklist entry.

    Separate from `RequirementVerdict` in `app/domain/screening.py` because that module is pure
    and knows nothing about documents or pages. The verdict decides the score; this decides what
    the buyer is shown as justification for it. `matched_document_id` is mandatory for a
    `present`/`present_expired` verdict — a match with nothing behind it is not a match
    (`CLAUDE.md`, and the `present_needs_document` check constraint).
    """

    document_type: RequiredDocumentType
    matched_document_id: uuid.UUID | None = None
    #: 1-based, and only meaningful alongside a matched document.
    source_page: int | None = None
    #: Verbatim text re-matched against the stored page before it reached this dataclass.
    evidence_quote: str | None = None
    #: The classifier's self-reported confidence. Advisory: it never scales the score.
    confidence: float | None = None
    #: Overrides the deterministic explanation, e.g. "licence expires before the closing date".
    note: str | None = None


def _count(quantity: int, noun: str) -> str:
    return f"{quantity} {noun}" if quantity == 1 else f"{quantity} {noun}s"


def build_screening_summary(result: ScreeningResult) -> str:
    """The advisory narrative stored on the screening row.

    Assembled from the *validated findings only* — counts, verdicts, and the controlled labels
    in `app/domain/screening.py`. No sentence here derives from document text, and none asserts
    that a vendor lacks a document (`CLAUDE.md`; `docs/09` §10.6).
    """
    if not result.findings:
        return (
            "This listing has no document requirements, so there was nothing to screen this "
            "application against."
        )

    assessed = result.mandatory_total + result.optional_total
    parts: list[str] = []

    if result.score is None:
        parts.append(
            "Every requirement on the checklist was marked as not applicable to this "
            "application, so no score was produced."
        )
    else:
        parts.append(
            f"This application scored {result.score} out of 100 against "
            f"{_count(assessed, 'assessed requirement')}."
        )

    parts.append(
        f"Mandatory documents matched: {result.mandatory_met} of {result.mandatory_total}. "
        f"Optional: {result.optional_met} of {result.optional_total}."
    )

    if result.missing:
        labels = ", ".join(finding.label for finding in result.missing)
        parts.append(f"Nothing in the documents supplied matched: {labels}. {NOT_PROOF_OF_ABSENCE}")

    if result.unreadable:
        labels = ", ".join(finding.label for finding in result.unreadable)
        parts.append(
            f"Supplied but could not be read: {labels}. A text-based PDF or a clearer scan "
            "would allow these to be assessed."
        )

    if result.has_blocking_gap:
        parts.append("At least one mandatory requirement is unmet.")

    return " ".join(parts)


def _require_loaded(entity: Any, attribute: str) -> None:
    """Fail with a precise message instead of a `MissingGreenlet` from deep inside serialisation.

    Under asyncio a lazy load raises, and the traceback points at whoever *touched* the
    relationship rather than at whoever failed to load it. This turns that into a sentence
    naming the loader to use.
    """
    if attribute in inspect(entity).unloaded:
        raise ValueError(
            f"{type(entity).__name__}.{attribute} is not loaded. Load the screening through "
            "ApplicationScreeningRepository.get_by_id, which eager-loads the application, its "
            "documents, and the listing checklist."
        )


class ScreeningService:
    def __init__(
        self,
        *,
        applications: ApplicationRepository,
        screenings: ApplicationScreeningRepository,
        notifications: NotificationService,
    ) -> None:
        self.applications = applications
        self.screenings = screenings
        self.notifications = notifications

    # --- Reads ---------------------------------------------------------------------------

    async def get_for_vendor(
        self, *, vendor_user_id: uuid.UUID, application_id: uuid.UUID
    ) -> ApplicationScreening:
        """The vendor's own screening result, polled while `pending` or `processing`."""
        application = await self.applications.get_for_vendor(application_id, vendor_user_id)
        if application is None:
            raise NotFoundError("Application not found.")
        return self._screening_of(application)

    async def get_for_listing_owner(
        self, *, owner_user_id: uuid.UUID, application_id: uuid.UUID
    ) -> ApplicationScreening:
        """The same result seen by the buyer whose listing was applied to.

        A different lookup, not a different filter afterwards: `get_for_listing_owner` joins the
        listing and filters on its owner, so an application ID from somebody else's listing
        produces no row and a 404 — the buyer learns nothing about it.
        """
        application = await self.applications.get_for_listing_owner(application_id, owner_user_id)
        if application is None:
            raise NotFoundError("Application not found.")
        return self._screening_of(application)

    @staticmethod
    def _screening_of(application: Application) -> ApplicationScreening:
        screening = application.screening
        if screening is None:
            # 404 rather than an empty body: until the vendor submits, this resource genuinely
            # does not exist.
            raise NotFoundError(NOT_SCREENED_DETAIL)
        return screening

    # --- Worker writes -------------------------------------------------------------------

    async def mark_processing(
        self, *, screening: ApplicationScreening, now: datetime | None = None
    ) -> ApplicationScreening:
        """Move a queued screening into `processing`.

        Clearing the previous score matters on a re-run: `application_screenings` enforces
        `status = 'completed' OR overall_score IS NULL`, so leaving a completed run's number in
        place while the status moves away from `completed` fails at flush.
        """
        screening.status = ScreeningStatus.PROCESSING.value
        screening.started_at = now or datetime.now(tz=UTC)
        screening.completed_at = None
        screening.overall_score = None
        screening.error_code = None
        await self.screenings.flush()
        logger.info("screening_processing", extra={"screening_id": str(screening.id)})
        return screening

    async def mark_failed(
        self,
        *,
        screening: ApplicationScreening,
        error_code: AnalysisErrorCode,
        now: datetime | None = None,
    ) -> ApplicationScreening:
        """Record a failed run and tell the vendor — nobody else.

        The failure is ours, not the applicant's, so the buyer is not notified and no score is
        written. The vendor may submit again (`docs/09` §4).
        """
        application = self._application_of(screening)
        listing = self._listing_of(application)

        screening.status = ScreeningStatus.FAILED.value
        screening.overall_score = None
        screening.error_code = error_code.value
        screening.completed_at = now or datetime.now(tz=UTC)

        self.notifications.screening_failed(
            vendor_user_id=application.vendor_user_id,
            listing_id=listing.id,
            listing_title=listing.title,
            application_id=application.id,
        )
        await self.screenings.flush()
        logger.warning(
            "screening_failed",
            extra={"screening_id": str(screening.id), "error_code": error_code.value},
        )
        return screening

    async def persist_result(
        self,
        *,
        screening: ApplicationScreening,
        result: ScreeningResult,
        evidence: Sequence[FindingEvidence] = (),
        documents_processed: int,
        pages_extracted: int,
        pages_needing_ocr: int,
        prompt_version: str | None = None,
        now: datetime | None = None,
    ) -> ApplicationScreening:
        """Write a completed screening: findings, score, counts, summary, and the notifications.

        Takes values that are already final. `result` came from
        `app.domain.screening.calculate_screening_score`, and every quote in `evidence` was
        re-matched against the stored page text before it got here — this method verifies
        neither, because a second, weaker check in a second place is how two checks start
        disagreeing.

        It does verify the one invariant that the database also enforces and that a classifier
        bug would otherwise turn into a 500 at commit: a `present` or `present_expired` verdict
        must name the document that satisfied it.

        `screening` must have been loaded by `ApplicationScreeningRepository.get_by_id`, whose
        eager loads this method depends on. Nothing is committed — the worker owns its
        transaction boundary, exactly as `app/workers/pipeline.py` does.
        """
        application = self._application_of(screening)
        listing = self._listing_of(application)
        _require_loaded(screening, "findings")
        by_type = self._index_evidence(evidence, result)
        completed_at = now or datetime.now(tz=UTC)

        # Replace the previous findings in their own flush. The unique constraint on
        # (screening_id, document_type) means a re-run's INSERTs cannot share a flush with the
        # DELETEs they supersede.
        screening.findings.clear()
        await self.screenings.flush()

        for order, finding in enumerate(result.findings):
            found = by_type.get(finding.document_type)
            if finding.verdict in MET_VERDICTS and (
                found is None or found.matched_document_id is None
            ):
                raise ValueError(
                    f"Verdict {finding.verdict.value} for {finding.document_type.value} names no "
                    "document. A match with nothing behind it must be demoted to 'missing' "
                    "before scoring, not stored."
                )
            screening.findings.append(
                ScreeningFinding(
                    document_type=finding.document_type.value,
                    verdict=finding.verdict.value,
                    is_mandatory=finding.is_mandatory,
                    weight=finding.weight,
                    matched_document_id=found.matched_document_id if found else None,
                    confidence=self._clean_confidence(found),
                    source_page=self._clean_page(found),
                    evidence_quote=found.evidence_quote if found else None,
                    # The deterministic explanation unless the pipeline had something more
                    # specific to say; both are written from validated records, never from
                    # document text.
                    note=(found.note if found and found.note else finding.explanation),
                    display_order=order,
                )
            )

        screening.status = ScreeningStatus.COMPLETED.value
        screening.overall_score = result.score
        screening.mandatory_met = result.mandatory_met
        screening.mandatory_total = result.mandatory_total
        screening.optional_met = result.optional_met
        screening.optional_total = result.optional_total
        screening.documents_processed = documents_processed
        screening.pages_extracted = pages_extracted
        screening.pages_needing_ocr = pages_needing_ocr
        screening.summary = build_screening_summary(result)
        # The module constant, not `settings.scoring_version`: the algorithm that produced this
        # number is the authority on which version produced it.
        screening.scoring_version = SCREENING_SCORING_VERSION
        if prompt_version is not None:
            screening.prompt_version = prompt_version
        screening.error_code = None
        screening.completed_at = completed_at

        self.notifications.screening_completed(
            owner_user_id=listing.owner_user_id,
            vendor_user_id=application.vendor_user_id,
            listing_id=listing.id,
            listing_title=listing.title,
            application_id=application.id,
            score=result.score,
            has_blocking_gap=result.has_blocking_gap,
        )

        await self.screenings.flush()
        logger.info(
            "screening_completed",
            extra={
                "screening_id": str(screening.id),
                "application_id": str(application.id),
                "score": result.score,
                "has_blocking_gap": result.has_blocking_gap,
                "pages_needing_ocr": pages_needing_ocr,
            },
        )
        return screening

    # --- Helpers -------------------------------------------------------------------------

    @staticmethod
    def _application_of(screening: ApplicationScreening) -> Application:
        _require_loaded(screening, "application")
        return screening.application

    @staticmethod
    def _listing_of(application: Application) -> TenderListing:
        _require_loaded(application, "listing")
        return application.listing

    @staticmethod
    def _index_evidence(
        evidence: Sequence[FindingEvidence], result: ScreeningResult
    ) -> Mapping[RequiredDocumentType, FindingEvidence]:
        """Key the evidence by document type, dropping anything the checklist did not ask for.

        Dropping rather than raising follows `app/ai/extraction.py`'s treatment of an
        out-of-range page: a proposal about a requirement that is not on this listing is noise
        from the classifier, and discarding it costs nothing. A *duplicate* is different — two
        pieces of evidence for one requirement means the caller has two answers and no way to
        say which was scored, so it fails loudly.
        """
        wanted = {finding.document_type for finding in result.findings}
        indexed: dict[RequiredDocumentType, FindingEvidence] = {}
        for item in evidence:
            if item.document_type not in wanted:
                logger.warning(
                    "screening_evidence_off_checklist",
                    extra={"document_type": item.document_type.value},
                )
                continue
            if item.document_type in indexed:
                raise ValueError(
                    f"Two pieces of evidence were supplied for {item.document_type.value}; "
                    "exactly one finding is written per checklist entry."
                )
            indexed[item.document_type] = item
        return indexed

    @staticmethod
    def _clean_confidence(found: FindingEvidence | None) -> Decimal | None:
        """Quantise to the column, and clamp into the constraint's range.

        A model's self-reported confidence is not calibrated and occasionally lands outside
        0-1. Clamping keeps an advisory number advisory; failing the whole run over it would
        discard a screening that is otherwise complete and correct.
        """
        if found is None or found.confidence is None:
            return None
        clamped = min(max(found.confidence, 0.0), 1.0)
        return Decimal(str(clamped)).quantize(_CONFIDENCE_QUANTUM)

    @staticmethod
    def _clean_page(found: FindingEvidence | None) -> int | None:
        """Drop a page number that cannot be real, as requirement extraction already does."""
        if found is None or found.source_page is None:
            return None
        if found.source_page < 1:
            logger.warning(
                "screening_evidence_page_invalid",
                extra={
                    "document_type": found.document_type.value,
                    "source_page": found.source_page,
                },
            )
            return None
        return found.source_page
