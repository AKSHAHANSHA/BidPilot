"""Tender-listing orchestration: a buyer's own listings and the public catalogue.

Three kinds of rule live here, all of them things a route handler must not decide:

* **Lifecycle preconditions.** `publish` and `close` are transitions, not field assignments.
  Publishing is gated on the listing being biddable at all — a deadline in the future, a brief
  to bid against, and a checklist to be screened against — and every failed precondition is
  reported in one message, because a buyer fixing their listing one 422 at a time is a buyer
  who gives up.
* **Rules that need the persisted row.** A `PATCH` carrying only `budget_max` can only be judged
  against the stored `budget_min`, exactly as `CompanyService` judges a partial project update.
* **Rules that need another table.** The document checklist cannot be rewritten once bids have
  been screened against it, and that fact lives in `applications`.

Reads never mutate. A listing whose deadline has passed is *presented* as closed by
:func:`derive_display_status`; the row is only rewritten by the buyer calling `/close` or by the
scheduled close job. Deriving it means a read path can never write, and the catalogue tells the
truth in the window between a deadline passing and the job running.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.api.errors import ConflictError, NotFoundError, ValidationProblem
from app.core.config import Settings
from app.core.logging import get_logger
from app.domain.enums import ApplicationStatus, ListingStatus, TenderCategory
from app.models.listing import ListingDocumentRequirement, TenderListing
from app.repositories.application_repository import ApplicationRepository
from app.repositories.listing_repository import (
    ListingFilters,
    PortalStats,
    TenderListingRepository,
)
from app.repositories.organisation_repository import OrganisationRepository
from app.schemas.listing import (
    DocumentRequirementWrite,
    ListingCreate,
    ListingUpdate,
    label_for,
)

logger = get_logger(__name__)

#: Columns the database declares `NOT NULL`. `ListingUpdate` types them as optional so the field
#: can be *omitted*, which means an explicit `null` also validates — and would reach the database
#: as an IntegrityError, i.e. a 500 for what is really a bad request. Rejected here by name.
_NOT_NULLABLE_FIELDS = frozenset(
    {
        "title",
        "summary",
        "description",
        "category",
        "emirate",
        "currency",
        "tags",
        "required_certifications",
        "requires_bid_bond",
    }
)

#: Statuses whose terms are settled. Editing a listing after it stopped accepting bids would
#: rewrite the brief people actually bid against, which no audit could reconstruct afterwards.
_EDITABLE_STATUSES = frozenset({ListingStatus.DRAFT.value, ListingStatus.PUBLISHED.value})

#: Page size for walking a listing's applicants when it closes. Every applicant must be
#: notified, so this pages to exhaustion rather than truncating at an arbitrary limit and
#: quietly leaving the tail of the list uninformed.
_CLOSURE_PAGE_SIZE = 200


@dataclass(frozen=True, slots=True)
class ClosureNotice:
    """One vendor who has to be told a listing closed (`docs/09` §9)."""

    application_id: uuid.UUID
    vendor_user_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class ListingClosure:
    """The outcome of closing a listing, plus who is owed a notification.

    The notification rows are written by the notification service, not here: they belong to the
    same unit of work as this transition, but composing the wording is that service's job.
    """

    listing: TenderListing
    notices: tuple[ClosureNotice, ...]


@dataclass(frozen=True, slots=True)
class CategoryTally:
    """One row of `GET /public/categories` before it is shaped into a response."""

    category: TenderCategory
    count: int


def _as_utc(value: datetime) -> datetime:
    """Treat a naive timestamp as UTC rather than raising mid-comparison.

    The columns are `DateTime(timezone=True)` and Postgres returns aware values, so this only
    fires for rows written by a script or a fixture. Degrading to a wrong-by-hours comparison
    beats turning an ordinary catalogue read into a 500.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def derive_display_status(listing: TenderListing, *, now: datetime | None = None) -> ListingStatus:
    """What the listing *is* right now, which is not always what the column says.

    A published listing whose submission deadline has passed is closed in every sense that
    matters to a visitor: nothing more can be bid. The column still reads `published` until the
    buyer closes it or the scheduled job does, and rewriting it from a `GET` would make an
    unauthenticated read a write. So it is derived, on every read, and never stored.
    """
    status = ListingStatus(listing.status)
    if status is not ListingStatus.PUBLISHED:
        return status
    deadline = listing.submission_deadline
    if deadline is not None and _as_utc(deadline) <= (now or datetime.now(tz=UTC)):
        return ListingStatus.CLOSED
    return status


def is_open_for_applications(listing: TenderListing, *, now: datetime | None = None) -> bool:
    """Whether a vendor may still apply. The one question the application service must ask."""
    return derive_display_status(listing, now=now) is ListingStatus.PUBLISHED


class ListingService:
    def __init__(
        self,
        *,
        listings: TenderListingRepository,
        organisations: OrganisationRepository,
        applications: ApplicationRepository,
        settings: Settings,
    ) -> None:
        self.listings = listings
        self.organisations = organisations
        self.applications = applications
        self.settings = settings

    # --- Buyer-owned listings ------------------------------------------------------------

    async def create_listing(self, *, user_id: uuid.UUID, payload: ListingCreate) -> TenderListing:
        """Stage a new draft. Never publishes — that transition has preconditions."""
        organisation = await self.organisations.get_for_owner(user_id)
        if organisation is None:
            # Registration creates the organisation in the same transaction as the user, so this
            # is a data fault rather than a normal flow. It still gets a usable message instead
            # of a NULL foreign key.
            raise ValidationProblem(
                "This account has no organisation, so it cannot publish listings."
            )

        if payload.reference is not None and await self.listings.reference_exists(
            organisation.id, payload.reference
        ):
            raise ConflictError(
                f"Reference {payload.reference!r} is already used by another of your listings."
            )

        values: dict[str, Any] = payload.model_dump()
        # Stored as plain values: the columns are `String` with CHECK constraints, not database
        # enums, so the member itself would not round-trip cleanly.
        values["category"] = payload.category.value
        values["emirate"] = payload.emirate.value

        listing = TenderListing(
            owner_user_id=user_id,
            # The relationship, not the id: it populates `organisation_id` at flush *and* leaves
            # the attribute loaded, so serialising `ListingDetail.organisation` afterwards does
            # not trigger a lazy load (which raises under asyncio). Same reason for the empty
            # checklist — a new draft has no requirements, and saying so beats fetching it.
            organisation=organisation,
            document_requirements=[],
            status=ListingStatus.DRAFT.value,
            **values,
        )
        self.listings.add(listing)
        await self.listings.flush()
        logger.info(
            "listing_created",
            extra={"listing_id": str(listing.id), "category": listing.category},
        )
        return listing

    async def get_listing(self, *, user_id: uuid.UUID, listing_id: uuid.UUID) -> TenderListing:
        listing = await self.listings.get_for_owner(listing_id, user_id)
        if listing is None:
            # 404 rather than 403 whether the row is absent or another buyer's: a 403 would
            # confirm that a listing with this id exists somewhere in the marketplace.
            raise NotFoundError("Listing not found.")
        return listing

    async def list_listings(
        self,
        *,
        user_id: uuid.UUID,
        status: ListingStatus | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[TenderListing], int]:
        """The buyer's own listings, drafts included."""
        return await self.listings.list_for_owner(
            user_id, status=status, limit=limit, offset=offset
        )

    async def update_listing(
        self, *, user_id: uuid.UUID, listing_id: uuid.UUID, payload: ListingUpdate
    ) -> TenderListing:
        listing = await self.get_listing(user_id=user_id, listing_id=listing_id)
        if listing.status not in _EDITABLE_STATUSES:
            raise ConflictError(
                f"A {label_for(listing.status).lower()} listing can no longer be edited. "
                "Its terms are the ones applicants bid against."
            )

        # `exclude_unset` is the whole point of PATCH: it distinguishes "field absent" from
        # "field explicitly set to null", and the two mean different things below.
        changes: dict[str, Any] = payload.model_dump(exclude_unset=True)
        for field in _NOT_NULLABLE_FIELDS & changes.keys():
            if changes[field] is None:
                raise ValidationProblem(f"'{field}' is required and cannot be cleared.")

        if changes.get("category") is not None and payload.category is not None:
            changes["category"] = payload.category.value
        if changes.get("emirate") is not None and payload.emirate is not None:
            changes["emirate"] = payload.emirate.value

        self._validate_update(listing, changes, now=datetime.now(tz=UTC))

        reference = changes.get("reference")
        if (
            reference is not None
            and reference != listing.reference
            and await self.listings.reference_exists(
                listing.organisation_id, reference, exclude_listing_id=listing.id
            )
        ):
            raise ConflictError(
                f"Reference {reference!r} is already used by another of your listings."
            )

        for field, value in changes.items():
            setattr(listing, field, value)

        await self.listings.flush()
        logger.info(
            "listing_updated",
            extra={"listing_id": str(listing.id), "fields_changed": len(changes)},
        )
        return listing

    def _validate_update(
        self, listing: TenderListing, changes: dict[str, Any], *, now: datetime
    ) -> None:
        """Cross-field rules the schema cannot check, because only one half may have arrived."""
        minimum = changes.get("budget_min", listing.budget_min)
        maximum = changes.get("budget_max", listing.budget_max)
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValidationProblem("Minimum budget cannot exceed the maximum budget.")

        submission = changes.get("submission_deadline", listing.submission_deadline)
        questions = changes.get("questions_deadline", listing.questions_deadline)
        if submission is not None and questions is not None and questions > submission:
            raise ValidationProblem(
                "The questions deadline cannot be later than the submission deadline."
            )

        requires_bond = changes.get("requires_bid_bond", listing.requires_bid_bond)
        percentage = changes.get("bid_bond_percentage", listing.bid_bond_percentage)
        if percentage is not None and not requires_bond:
            raise ValidationProblem("A bid bond percentage requires requires_bid_bond to be true.")

        if listing.status == ListingStatus.DRAFT.value or "submission_deadline" not in changes:
            return
        # A live listing losing its deadline violates the `published_needs_deadline` constraint,
        # and one gaining a past deadline would close silently — with no notification to the
        # vendors already working on a bid. Both are refused; `/close` is the honest route.
        if submission is None:
            raise ValidationProblem(
                "A published listing must keep a submission deadline. Close it instead."
            )
        if _as_utc(submission) <= now:
            raise ValidationProblem(
                "A new submission deadline must be in the future. Use the close endpoint to "
                "end a listing early."
            )

    # --- Lifecycle -----------------------------------------------------------------------

    async def publish(self, *, user_id: uuid.UUID, listing_id: uuid.UUID) -> TenderListing:
        """Make a draft public, if it is actually biddable.

        Every unmet precondition is named in one message. Reporting them one per request would
        make a buyer discover the checklist requirement only after two earlier round trips, and
        the third failure reads as the product being broken rather than the listing being
        incomplete.
        """
        listing = await self.get_listing(user_id=user_id, listing_id=listing_id)
        if listing.status != ListingStatus.DRAFT.value:
            raise ConflictError(
                f"Only a draft can be published; this listing is "
                f"{label_for(listing.status).lower()}."
            )

        now = datetime.now(tz=UTC)
        missing: list[str] = []
        if listing.submission_deadline is None:
            missing.append("a submission deadline")
        elif _as_utc(listing.submission_deadline) <= now:
            missing.append("a submission deadline in the future (the one set has passed)")
        if not listing.description.strip():
            missing.append("a description for bidders to work from")
        if not any(requirement.is_mandatory for requirement in listing.document_requirements):
            # Without a mandatory requirement every applicant screens identically and the score
            # ranks nothing. Publishing that is worse than refusing: the buyer would believe
            # their applicants had been checked.
            missing.append("at least one mandatory document requirement")

        if missing:
            raise ValidationProblem(
                "This listing is not ready to publish. It still needs " + _join(missing) + "."
            )

        listing.status = ListingStatus.PUBLISHED.value
        listing.published_at = now
        await self.listings.flush()
        logger.info(
            "listing_published",
            extra={
                "listing_id": str(listing.id),
                "requirements": len(listing.document_requirements),
            },
        )
        return listing

    async def close(self, *, user_id: uuid.UUID, listing_id: uuid.UUID) -> ListingClosure:
        """End the bidding window and report who must be told.

        The notification rows are the notification service's to write, but they belong to *this*
        transaction: if the close is rolled back, nobody may be left holding a message about a
        listing that is still open.
        """
        listing = await self.get_listing(user_id=user_id, listing_id=listing_id)
        if listing.status != ListingStatus.PUBLISHED.value:
            raise ConflictError(
                f"Only a published listing can be closed; this one is "
                f"{label_for(listing.status).lower()}."
            )

        listing.status = ListingStatus.CLOSED.value
        notices = await self._closure_notices(listing_id=listing.id, owner_user_id=user_id)
        await self.listings.flush()
        logger.info(
            "listing_closed",
            extra={"listing_id": str(listing.id), "applicants_notified": len(notices)},
        )
        return ListingClosure(listing=listing, notices=notices)

    async def _closure_notices(
        self, *, listing_id: uuid.UUID, owner_user_id: uuid.UUID
    ) -> tuple[ClosureNotice, ...]:
        """Every applicant owed a `listing_closed` notification.

        Withdrawn applications are skipped: a vendor who pulled out has no stake in the outcome,
        and telling them anyway is noise they never asked for.
        """
        notices: list[ClosureNotice] = []
        offset = 0
        while True:
            rows, total = await self.applications.list_for_listing(
                listing_id, owner_user_id, limit=_CLOSURE_PAGE_SIZE, offset=offset
            )
            notices.extend(
                ClosureNotice(application_id=row.id, vendor_user_id=row.vendor_user_id)
                for row in rows
                if row.status != ApplicationStatus.WITHDRAWN.value
            )
            offset += len(rows)
            if not rows or offset >= total:
                return tuple(notices)

    # --- Document checklist --------------------------------------------------------------

    async def replace_requirements(
        self,
        *,
        user_id: uuid.UUID,
        listing_id: uuid.UUID,
        items: Sequence[DocumentRequirementWrite],
    ) -> TenderListing:
        """Replace the whole checklist.

        Refused once anything has been submitted. Those bids were screened against the old list
        and their stored scores would silently start describing a checklist nobody was asked to
        satisfy — a number that is wrong and looks right is worse than no number at all.
        """
        listing = await self.get_listing(user_id=user_id, listing_id=listing_id)

        # The request schema rejects duplicates too, but the rule belongs to the service: it is
        # a database constraint, and any future caller reaching this method must hit it.
        seen: set[str] = set()
        for item in items:
            if item.document_type.value in seen:
                raise ValidationProblem(
                    f"The checklist lists {label_for(item.document_type)} twice."
                )
            seen.add(item.document_type.value)

        _, submitted = await self.applications.list_for_listing(
            listing_id, user_id, limit=1, offset=0
        )
        if submitted:
            raise ConflictError(
                f"This listing already has {submitted} submitted "
                f"{'application' if submitted == 1 else 'applications'}, screened against the "
                "current checklist. Changing it now would leave those scores describing "
                "requirements the applicants were never given."
            )

        # Cleared and flushed *before* the replacements are staged. A single flush would order
        # the INSERTs ahead of the DELETEs and any document type kept from the old checklist
        # would collide with `uq_listing_document_requirements_listing_type`.
        listing.document_requirements.clear()
        await self.listings.flush()

        listing.document_requirements.extend(
            ListingDocumentRequirement(
                listing_id=listing.id,
                document_type=item.document_type.value,
                is_mandatory=item.is_mandatory,
                weight=item.weight,
                notes=item.notes,
                # Position in the request body *is* the display order, so a body cannot carry an
                # arrangement that contradicts itself.
                display_order=index,
            )
            for index, item in enumerate(items)
        )
        await self.listings.flush()
        logger.info(
            "listing_requirements_replaced",
            extra={
                "listing_id": str(listing.id),
                "requirements": len(items),
                "mandatory": sum(1 for item in items if item.is_mandatory),
            },
        )
        return listing

    # --- Public catalogue ----------------------------------------------------------------

    async def list_public(
        self, *, filters: ListingFilters, limit: int, offset: int
    ) -> tuple[list[TenderListing], int]:
        """One page of the catalogue. Published only — the repository hard-codes that."""
        return await self.listings.list_public(filters, limit=limit, offset=offset)

    async def get_public(self, listing_id: uuid.UUID) -> TenderListing:
        listing = await self.listings.get_public(listing_id)
        if listing is None:
            raise NotFoundError("Listing not found.")
        return listing

    async def category_counts(self) -> list[CategoryTally]:
        """All 30 categories, zero-count ones included.

        The landing page renders the whole taxonomy; a category that vanished when its last
        listing closed would make the navigation flicker. SQL returns only the non-empty rows
        and the zeros are filled from the enum, which is the authority on what exists.
        """
        counts = dict(await self.listings.category_counts())
        tallies = [
            CategoryTally(category=category, count=counts.get(category.value, 0))
            for category in TenderCategory
        ]
        # Busiest first, then alphabetically by the label the user actually reads — sorting by
        # the raw enum value would order "ai_data_analytics" before "AI Data Analytics" expects.
        tallies.sort(key=lambda tally: (-tally.count, label_for(tally.category)))
        return tallies

    async def portal_stats(self) -> PortalStats:
        return await self.listings.portal_stats()


def _join(items: list[str]) -> str:
    """Oxford-free "a, b and c" — this text is read by a person fixing their listing."""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]
