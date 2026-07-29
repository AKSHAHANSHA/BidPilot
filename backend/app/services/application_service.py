"""Application orchestration: the vendor's bid from draft to decision.

Two callers with opposite interests share this service, and every method belongs to exactly
one of them. Vendor-side methods resolve the application through `get_for_vendor`
(`vendor_user_id` in the `WHERE` clause); buyer-side methods resolve it through
`get_for_listing_owner`, which joins `tender_listings` and filters on its owner. There is no
method here that takes an application ID alone.

Three flows are copied deliberately from code that already works:

* uploads follow `TenderService.upload_document` — validate the *bytes*, dedupe on SHA-256,
  generate the storage key server-side, and delete the stored file if the row fails to land;
* submission follows `AnalysisService.create_analysis` — write the row, **commit**, then
  enqueue, because the worker runs in a different transaction and cannot see uncommitted work;
* the money aggregates follow `docs/09` §6, where an undefined ratio is null rather than zero.

An application is immutable to the vendor once submitted. Editing a bid the buyer is already
reading — or attaching a document after screening scored the submission — would make the
applicant list a description of something that no longer exists.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from sqlalchemy.exc import IntegrityError

from app.api.errors import ConflictError, NotFoundError, ValidationProblem
from app.core.config import Settings
from app.core.logging import get_logger
from app.documents.extraction import extract_pdf_pages
from app.documents.validation import validate_pdf_upload
from app.domain.enums import (
    ApplicationStatus,
    ListingStatus,
    RequiredDocumentType,
    ScreeningStatus,
)
from app.domain.screening import SCREENING_SCORING_VERSION
from app.models.application import Application, ApplicationDocument
from app.models.listing import TenderListing
from app.models.screening import ApplicationScreening
from app.repositories.application_repository import (
    ApplicationRepository,
    ApplicationScreeningRepository,
)
from app.repositories.listing_repository import TenderListingRepository
from app.repositories.organisation_repository import OrganisationRepository
from app.schemas.application import (
    ApplicationCreate,
    ApplicationDecision,
    ApplicationUpdate,
    VendorStats,
)
from app.services.notification_service import NotificationService
from app.storage.base import StorageBackend

logger = get_logger(__name__)

DRAFT_ONLY_DETAIL = (
    "A submitted application can no longer be changed. Withdraw it if you need to stop it "
    "being considered."
)


class ScreeningQueue(Protocol):
    """The one queue method this service needs (`docs/09` §4).

    Declared here rather than imported from `app.workers.queue` because `JobQueue` does not
    carry `enqueue_screening` yet and that module belongs to the worker. Both adapters satisfy
    this protocol structurally the moment they grow the method — there is nothing to inherit
    and nothing to register.
    """

    async def enqueue_screening(self, screening_id: uuid.UUID) -> None: ...


class ApplicationService:
    def __init__(
        self,
        *,
        applications: ApplicationRepository,
        screenings: ApplicationScreeningRepository,
        listings: TenderListingRepository,
        organisations: OrganisationRepository,
        notifications: NotificationService,
        storage: StorageBackend,
        job_queue: ScreeningQueue,
        settings: Settings,
    ) -> None:
        self.applications = applications
        self.screenings = screenings
        self.listings = listings
        self.organisations = organisations
        self.notifications = notifications
        self.storage = storage
        self.job_queue = job_queue
        self.settings = settings

    # --- Guards ------------------------------------------------------------------------

    @staticmethod
    def _now() -> datetime:
        return datetime.now(tz=UTC)

    async def _get_for_vendor(
        self, application_id: uuid.UUID, vendor_user_id: uuid.UUID
    ) -> Application:
        application = await self.applications.get_for_vendor(application_id, vendor_user_id)
        if application is None:
            raise NotFoundError("Application not found.")
        return application

    async def _get_for_listing_owner(
        self, application_id: uuid.UUID, owner_user_id: uuid.UUID
    ) -> Application:
        application = await self.applications.get_for_listing_owner(application_id, owner_user_id)
        if application is None:
            # 404, not 403: an application on somebody else's listing must not be confirmable.
            raise NotFoundError("Application not found.")
        return application

    @staticmethod
    def _require_draft(application: Application) -> None:
        if application.status != ApplicationStatus.DRAFT.value:
            raise ConflictError(DRAFT_ONLY_DETAIL)

    def _require_open(self, listing: TenderListing) -> None:
        """The listing must still be accepting bids.

        Checked on create *and* on submit: a draft can sit for days, and the deadline it was
        started against may well have passed by the time the vendor presses send.
        """
        if listing.status != ListingStatus.PUBLISHED.value:
            raise ConflictError("This listing is no longer accepting applications.")
        deadline = listing.submission_deadline
        if deadline is not None and deadline <= self._now():
            raise ConflictError("The submission deadline for this listing has passed.")

    # --- Vendor: the application record --------------------------------------------------

    async def create(self, *, vendor_user_id: uuid.UUID, payload: ApplicationCreate) -> Application:
        """Start a draft against a published listing.

        `get_public` is the lookup on purpose: it restricts to `status='published'`, so a draft
        or cancelled listing is a 404 here for the same reason it is one in the catalogue.
        """
        listing = await self.listings.get_public(payload.listing_id)
        if listing is None:
            raise NotFoundError("Listing not found.")
        self._require_open(listing)

        organisation = await self.organisations.get_for_owner(vendor_user_id)
        if organisation is None:
            raise ValidationProblem(
                "Your account has no organisation, so an application cannot identify who is "
                "bidding."
            )

        existing = await self.applications.get_by_listing_and_vendor(listing.id, vendor_user_id)
        if existing is not None:
            raise ConflictError(
                "You already have an application to this listing. Edit that one instead of "
                "starting another.",
                extra={"existing_application_id": str(existing.id)},
            )

        application = Application(
            listing_id=listing.id,
            vendor_user_id=vendor_user_id,
            vendor_organisation_id=organisation.id,
            status=ApplicationStatus.DRAFT.value,
            cover_letter=payload.cover_letter,
            bid_amount=payload.bid_amount,
            estimated_cost=payload.estimated_cost,
            proposed_duration_months=payload.proposed_duration_months,
            # Every relationship the vendor's response shape reads is populated here, and that
            # is load-bearing rather than tidy. Once the row is flushed it is persistent, and
            # the first touch of an unset relationship emits a lazy load — which raises under
            # asyncio, inside the serialiser, after the write succeeded. `listing` is the object
            # already fetched above; a new draft genuinely has no documents and no screening.
            listing=listing,
            documents=[],
            screening=None,
        )
        self.applications.add(application)
        try:
            await self.applications.flush()
        except IntegrityError as exc:
            # The check above loses to a double-submitted form; the unique constraint does not.
            if "uq_applications_listing_vendor" in str(exc.orig):
                raise ConflictError("You already have an application to this listing.") from exc
            raise

        logger.info(
            "application_created",
            extra={"application_id": str(application.id), "listing_id": str(listing.id)},
        )
        return application

    async def get(self, *, vendor_user_id: uuid.UUID, application_id: uuid.UUID) -> Application:
        return await self._get_for_vendor(application_id, vendor_user_id)

    async def list_applications(
        self,
        *,
        vendor_user_id: uuid.UUID,
        status: ApplicationStatus | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[Application], int]:
        return await self.applications.list_for_vendor(
            vendor_user_id, status=status, limit=limit, offset=offset
        )

    async def update(
        self,
        *,
        vendor_user_id: uuid.UUID,
        application_id: uuid.UUID,
        payload: ApplicationUpdate,
    ) -> Application:
        """Edit a draft. Every field maps one-to-one onto a column, so no translation is needed."""
        application = await self._get_for_vendor(application_id, vendor_user_id)
        self._require_draft(application)

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(application, field, value)
        await self.applications.flush()
        logger.info("application_updated", extra={"application_id": str(application.id)})
        return application

    # --- Vendor: documents ---------------------------------------------------------------

    async def upload_document(
        self,
        *,
        vendor_user_id: uuid.UUID,
        application_id: uuid.UUID,
        content: bytes,
        original_filename: str | None,
        declared_document_type: RequiredDocumentType | None = None,
    ) -> ApplicationDocument:
        """Validate, store, and record one file attached to a draft application.

        Same compensation as `TenderService.upload_document`: the object is written first, the
        row second, and a failed row deletes the object before the error propagates, so a failed
        request leaves neither half behind.

        The PDF is parsed here but its pages are not stored. Parsing rejects a corrupt,
        encrypted, or oversized file at the door and yields a real page count; extraction proper
        belongs to the screening pipeline, which re-reads the bytes with OCR available
        (`docs/09` §4, §7). `extraction_status` therefore stays `pending` — calling a scanned
        document unsupported before OCR has had a chance would be a verdict, not a fact.
        """
        application = await self._get_for_vendor(application_id, vendor_user_id)
        self._require_draft(application)

        # The collection is eager-loaded, so the limit and the duplicate check below cost no
        # extra queries.
        if len(application.documents) >= self.settings.max_application_documents:
            raise ValidationProblem(
                f"An application may carry at most {self.settings.max_application_documents} "
                "documents. Remove one before uploading another."
            )

        validated = validate_pdf_upload(
            content=content,
            original_filename=original_filename,
            max_bytes=self.settings.max_upload_bytes,
        )

        duplicate = next(
            (doc for doc in application.documents if doc.sha256 == validated.sha256), None
        )
        if duplicate is not None:
            raise ConflictError(
                f"This file is already attached to the application as "
                f"'{duplicate.original_filename}' (identical SHA-256).",
                extra={"existing_document_id": str(duplicate.id)},
            )

        # PyMuPDF is CPU-bound synchronous code; on the event loop it would stall every other
        # request for the length of the parse.
        extraction = await asyncio.to_thread(
            extract_pdf_pages, validated.content, max_pages=self.settings.max_pdf_pages
        )

        stored_filename = f"{uuid.uuid4().hex}.pdf"
        # Server-generated, and rooted at the vendor: the client's filename never becomes part
        # of a key.
        storage_key = f"{vendor_user_id}/applications/{application.id}/{stored_filename}"

        await self.storage.save(storage_key, validated.content)

        document = ApplicationDocument(
            application_id=application.id,
            vendor_user_id=vendor_user_id,
            original_filename=validated.safe_original_filename,
            stored_filename=stored_filename,
            storage_key=storage_key,
            mime_type="application/pdf",
            size_bytes=validated.size_bytes,
            sha256=validated.sha256,
            page_count=extraction.page_count,
            declared_document_type=(
                declared_document_type.value if declared_document_type else None
            ),
        )
        application.documents.append(document)
        try:
            await self.applications.flush()
        except IntegrityError as exc:
            await self.storage.delete(storage_key)
            if "uq_application_documents_application_sha256" in str(exc.orig):
                raise ConflictError(
                    "This file is already attached to the application (identical SHA-256)."
                ) from exc
            raise
        except Exception:
            await self.storage.delete(storage_key)
            raise

        logger.info(
            "application_document_uploaded",
            extra={
                "application_id": str(application.id),
                "document_id": str(document.id),
                "size_bytes": document.size_bytes,
                "page_count": document.page_count,
            },
        )
        return document

    async def delete_document(
        self,
        *,
        vendor_user_id: uuid.UUID,
        application_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> None:
        """Remove a file from a draft. The row goes first, then the object.

        The database is the source of truth: a file whose row is gone wastes disk and is logged
        for cleanup, whereas a row whose file is gone is a document the screening pipeline
        cannot read.
        """
        application = await self._get_for_vendor(application_id, vendor_user_id)
        self._require_draft(application)

        document = next((doc for doc in application.documents if doc.id == document_id), None)
        if document is None:
            raise NotFoundError("Document not found on this application.")

        storage_key = document.storage_key
        application.documents.remove(document)  # delete-orphan turns this into a DELETE
        await self.applications.flush()

        if not await self.storage.delete(storage_key):
            logger.warning("orphan_file_cleanup_missed", extra={"storage_key": storage_key})
        logger.info(
            "application_document_deleted",
            extra={"application_id": str(application.id), "document_id": str(document_id)},
        )

    # --- Vendor: lifecycle ---------------------------------------------------------------

    async def submit(
        self, *, vendor_user_id: uuid.UUID, application_id: uuid.UUID
    ) -> tuple[Application, bool]:
        """Send the bid and queue its screening.

        Returns `(application, enqueued)`. `enqueued=False` means the call changed nothing: the
        application was already with the buyer and its screening is not in a failed state.
        Pressing submit twice must not tell the buyer twice, count twice, or run the pipeline
        twice.

        Resubmitting *is* meaningful in one case, which `docs/09` §4 calls for: a screening that
        failed can be re-run. That path re-queues the job without touching `submitted_at` or the
        listing's applicant counter, because the application was already submitted and already
        counted.

        The commit before enqueuing is not optional — the worker reads the screening row from
        its own transaction and would find nothing.
        """
        application = await self._get_for_vendor(application_id, vendor_user_id)
        listing = application.listing
        screening = application.screening

        if application.status == ApplicationStatus.WITHDRAWN.value:
            raise ConflictError(
                "This application was withdrawn. Withdrawing is final; apply again only if the "
                "buyer reopens the listing."
            )

        already_submitted = application.status != ApplicationStatus.DRAFT.value
        retrying = screening is not None and screening.status == ScreeningStatus.FAILED.value
        if already_submitted and not retrying:
            return application, False

        if not application.documents:
            raise ValidationProblem(
                "Attach at least one document before submitting; screening has nothing to "
                "assess otherwise."
            )

        now = self._now()
        if not already_submitted:
            # Only a first submission has to beat the deadline. Re-running a screening that
            # failed does not change the bid, and refusing it after the window closed would
            # leave the buyer looking at an unscored applicant because of our own failure.
            self._require_open(listing)
            application.status = ApplicationStatus.SUBMITTED.value
            application.submitted_at = now
            await self.applications.flush()
            # A single atomic UPDATE in the database, never a read-modify-write here: two
            # vendors submitting in the same window would otherwise both write the same count.
            await self.listings.increment_application_count(listing.id)
            self.notifications.application_received(
                owner_user_id=listing.owner_user_id,
                listing_id=listing.id,
                listing_title=listing.title,
                application_id=application.id,
            )

        if screening is None:
            screening = ApplicationScreening(
                application_id=application.id,
                status=ScreeningStatus.PENDING.value,
                scoring_version=SCREENING_SCORING_VERSION,
            )
            self.screenings.add(screening)
            # Wire it into the object graph as well as the session. The application in front of
            # us was loaded with `screening` already resolved to None; leaving it that way would
            # hand the caller a row that says it has no screening moments after one was created.
            application.screening = screening
        else:
            # A re-run starts from a clean row. The score must go with it: the table forbids a
            # score on anything other than a completed screening.
            screening.status = ScreeningStatus.PENDING.value
            screening.overall_score = None
            screening.error_code = None
            screening.summary = None
            screening.started_at = None
            screening.completed_at = None
        await self.screenings.flush()

        screening_id = screening.id
        await self.applications.session.commit()

        await self.job_queue.enqueue_screening(screening_id)
        logger.info(
            "application_submitted",
            extra={
                "application_id": str(application.id),
                "listing_id": str(listing.id),
                "screening_id": str(screening_id),
                "retry": retrying,
            },
        )
        # Re-read rather than `refresh`: refreshing expires the eager-loaded relationships the
        # response needs, and the eager queue used by tests has already run the whole pipeline
        # by now, so the caller should see the finished state.
        return await self._get_for_vendor(application_id, vendor_user_id), True

    async def withdraw(
        self, *, vendor_user_id: uuid.UUID, application_id: uuid.UUID
    ) -> Application:
        """Take a submitted bid out of consideration.

        Idempotent, and deliberately not available before or after the window in between: a
        draft was never sent (and `submitted_needs_timestamp` would reject the row), and a
        decided application is a matter of record the vendor cannot rewrite.
        """
        application = await self._get_for_vendor(application_id, vendor_user_id)

        if application.status == ApplicationStatus.WITHDRAWN.value:
            return application
        if application.status == ApplicationStatus.DRAFT.value:
            raise ConflictError(
                "This application has not been submitted, so there is nothing to withdraw."
            )
        if application.status in ApplicationStatus.decided_states():
            raise ConflictError(
                "The buyer has already decided this application; it can no longer be withdrawn."
            )

        application.status = ApplicationStatus.WITHDRAWN.value
        application.withdrawn_at = self._now()
        await self.applications.flush()
        await self.listings.decrement_application_count(application.listing_id)

        logger.info("application_withdrawn", extra={"application_id": str(application.id)})
        return application

    async def stats(self, *, vendor_user_id: uuid.UUID) -> VendorStats:
        """The dashboard counters (`docs/09` §6).

        The two ratios are `None`, never 0, when their denominator is zero. A win rate over no
        decisions is unknown, and rendering it as 0% would tell a vendor with three pending bids
        that they lose every time.
        """
        raw = await self.applications.vendor_stats(vendor_user_id)
        counts = raw.counts_by_status
        approved = counts[ApplicationStatus.APPROVED.value]
        rejected = counts[ApplicationStatus.REJECTED.value]
        decided = approved + rejected

        return VendorStats(
            draft=counts[ApplicationStatus.DRAFT.value],
            submitted=counts[ApplicationStatus.SUBMITTED.value],
            under_review=counts[ApplicationStatus.UNDER_REVIEW.value],
            shortlisted=counts[ApplicationStatus.SHORTLISTED.value],
            approved=approved,
            rejected=rejected,
            withdrawn=counts[ApplicationStatus.WITHDRAWN.value],
            waiting=raw.waiting,
            total_bid_value=raw.total_bid_value,
            total_margin=raw.total_margin,
            # Decimal division, then one conversion: the ratio is presentation, the money is not.
            margin_percentage=(
                None
                if raw.total_bid_value == Decimal(0)
                else float(raw.total_margin / raw.total_bid_value)
            ),
            win_rate=None if decided == 0 else approved / decided,
            incomplete_financials=raw.incomplete_financials,
        )

    # --- Buyer ---------------------------------------------------------------------------

    async def list_applicants(
        self,
        *,
        owner_user_id: uuid.UUID,
        listing_id: uuid.UUID,
        status: ApplicationStatus | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[Application], int]:
        """Applicants on one of the caller's listings, best screening score first.

        The listing is resolved first so a listing that is not the caller's answers 404 rather
        than an empty page, which would read as "nobody applied".
        """
        listing = await self.listings.get_for_owner(listing_id, owner_user_id)
        if listing is None:
            raise NotFoundError("Listing not found.")
        return await self.applications.list_for_listing(
            listing_id, owner_user_id, status=status, limit=limit, offset=offset
        )

    async def get_applicant(
        self, *, owner_user_id: uuid.UUID, application_id: uuid.UUID
    ) -> Application:
        return await self._get_for_listing_owner(application_id, owner_user_id)

    async def mark_under_review(
        self, *, owner_user_id: uuid.UUID, application_id: uuid.UUID
    ) -> Application:
        """Record that the buyer has opened this application.

        `submitted` and `under_review` exist as separate states so "waiting for an answer" means
        somebody has actually looked (`app/domain/enums.py`). `first_viewed_at` is written once
        and never overwritten — it is the first view, not the latest.

        No notification: being read is not a decision, and a message for it would train vendors
        to ignore the ones that are.
        """
        application = await self._get_for_listing_owner(application_id, owner_user_id)

        if application.first_viewed_at is None:
            application.first_viewed_at = self._now()
        if application.status == ApplicationStatus.SUBMITTED.value:
            application.status = ApplicationStatus.UNDER_REVIEW.value
            logger.info("application_under_review", extra={"application_id": str(application.id)})
        await self.applications.flush()
        return application

    async def decide(
        self,
        *,
        owner_user_id: uuid.UUID,
        application_id: uuid.UUID,
        payload: ApplicationDecision,
    ) -> Application:
        """Shortlist, approve, or reject — the buyer's verdict, and the vendor is told.

        The status vocabulary is already narrowed to those three by `ApplicationDecision`, so
        what is checked here is the *transition*: a withdrawn bid is no longer the buyer's to
        judge, and a decision already made is not silently overwritten.
        """
        application = await self._get_for_listing_owner(application_id, owner_user_id)

        if application.status == ApplicationStatus.WITHDRAWN.value:
            raise ConflictError("This application was withdrawn by the vendor.")
        if application.status in ApplicationStatus.decided_states():
            raise ConflictError(
                f"This application has already been {application.status}. A decision cannot be "
                "changed once the vendor has been told."
            )

        application.status = payload.status.value
        application.decided_at = self._now()
        application.decision_note = payload.note

        # `get_for_listing_owner` loads the applicant, not the listing, and the notification
        # needs the listing's title. Fetching it through the owner-scoped read keeps the
        # ownership check on the path that produces the message.
        listing = await self.listings.get_for_owner(application.listing_id, owner_user_id)
        if listing is None:  # pragma: no cover - the join above already proved ownership
            raise NotFoundError("Listing not found.")

        self.notifications.application_status_changed(
            vendor_user_id=application.vendor_user_id,
            listing_id=listing.id,
            listing_title=listing.title,
            application_id=application.id,
            status=payload.status,
            note=payload.note,
        )
        await self.applications.flush()

        logger.info(
            "application_decided",
            extra={"application_id": str(application.id), "status": application.status},
        )
        return application
