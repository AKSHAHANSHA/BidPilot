"""Tender-listing persistence — the public catalogue and the buyer's own listings.

Two audiences read this table and they must never share a query. Every method a visitor can
reach hard-codes ``status = 'published'``; the restriction lives here rather than in a service
so that no future caller can compose a public query that forgets it
(`docs/09_PORTAL_SPEC.md` §10.2). Everything a buyer reaches goes through `OwnedRepository`,
whose signatures demand the owner ID.

The public list is this application's hot path: a 24-card grid, unauthenticated, rendered on
every landing-page visit. It therefore does exactly two round trips — one count, one page —
and eager-loads the organisation and the document checklist with `selectinload`, because a
lazy load per card is 48 extra queries under `asyncio` (where a lazy load raises rather than
silently working).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, func, nulls_last, or_, select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.functions import concat

from app.domain.enums import Emirate, ListingStatus, TenderCategory
from app.models.listing import TenderListing
from app.repositories.base import OwnedRepository


class ListingSort(StrEnum):
    """Ordering options offered by `GET /public/listings` (`docs/09` §3.1).

    Not a `VocabularyEnum`: nothing persists a sort key, so there is no check constraint to
    keep in step. It lives beside the query that implements it so adding a member without
    adding an `ORDER BY` is impossible to miss.
    """

    DEADLINE = "deadline"
    NEWEST = "newest"
    BUDGET_HIGH = "budget_high"
    BUDGET_LOW = "budget_low"


@dataclass(frozen=True, slots=True)
class ListingFilters:
    """Public catalogue filters. All optional; all combine with AND."""

    category: TenderCategory | None = None
    emirate: Emirate | None = None
    #: Free text over title, summary, description, and tags.
    q: str | None = None
    #: A budget *floor* the visitor will consider, not the listing's own `budget_min`.
    budget_min: Decimal | None = None
    #: A budget *ceiling* the visitor will consider.
    budget_max: Decimal | None = None
    closing_within_days: int | None = None
    sort: ListingSort = ListingSort.DEADLINE


@dataclass(frozen=True, slots=True)
class PortalStats:
    """Landing-page hero counters, all over published listings only."""

    published_listings: int
    buyer_organisations: int
    total_value: Decimal
    categories: int


def _escape_like(term: str) -> str:
    """Neutralise LIKE metacharacters so a search for "100%" is a search, not a wildcard."""
    return term.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class TenderListingRepository(OwnedRepository[TenderListing]):
    model = TenderListing
    owner_field = "owner_user_id"

    #: Applied to every public read. A published listing is the only thing a visitor may see —
    #: drafts leak a buyer's unfinished work and closed/cancelled ones invite dead applications.
    @staticmethod
    def _published() -> ColumnElement[bool]:
        return TenderListing.status == ListingStatus.PUBLISHED.value

    @staticmethod
    def _card_options() -> tuple[Any, ...]:
        """Eager loads every listing card needs. Two extra queries total, not two per row."""
        return (
            selectinload(TenderListing.organisation),
            selectinload(TenderListing.document_requirements),
        )

    @staticmethod
    def _search_predicate(term: str) -> ColumnElement[bool]:
        """Case-insensitive substring match across the visitor-facing text.

        `ILIKE`, not full-text search: a demo catalogue holds hundreds of listings, and a
        tsvector column plus a maintenance trigger would buy nothing measurable here. Tags are
        flattened with `array_to_string` so one predicate covers the array too.
        """
        pattern = concat("%", _escape_like(term), "%")
        return or_(
            TenderListing.title.ilike(pattern, escape="\\"),
            TenderListing.summary.ilike(pattern, escape="\\"),
            TenderListing.description.ilike(pattern, escape="\\"),
            func.array_to_string(TenderListing.tags, " ").ilike(pattern, escape="\\"),
        )

    @staticmethod
    def _budget_ceiling() -> ColumnElement[Decimal | None]:
        """The most a listing might be worth. Falls back to `budget_min` when only one end of
        the range was disclosed."""
        return func.coalesce(TenderListing.budget_max, TenderListing.budget_min)

    @staticmethod
    def _budget_floor() -> ColumnElement[Decimal | None]:
        return func.coalesce(TenderListing.budget_min, TenderListing.budget_max)

    def _apply_public_filters(
        self,
        statement: Select[Any],
        filters: ListingFilters,
        *,
        now: datetime,
    ) -> Select[Any]:
        if filters.category is not None:
            statement = statement.where(TenderListing.category == filters.category.value)
        if filters.emirate is not None:
            statement = statement.where(TenderListing.emirate == filters.emirate.value)
        if filters.q:
            statement = statement.where(self._search_predicate(filters.q))

        # Range overlap, not point comparison: a listing quoted at 1M-3M matches a visitor
        # looking for work "above 2M". Listings that disclosed no budget at all drop out of a
        # budget-filtered search on their own — COALESCE of two NULLs is NULL, and NULL fails
        # every comparison — which is the honest answer: we cannot claim they match a range.
        if filters.budget_min is not None:
            statement = statement.where(self._budget_ceiling() >= filters.budget_min)
        if filters.budget_max is not None:
            statement = statement.where(self._budget_floor() <= filters.budget_max)

        if filters.closing_within_days is not None:
            # Bounded at both ends: "closing within 7 days" must not surface a listing whose
            # deadline already passed but whose close job has not run yet.
            statement = statement.where(
                TenderListing.submission_deadline.is_not(None),
                TenderListing.submission_deadline >= now,
                TenderListing.submission_deadline
                <= now + timedelta(days=filters.closing_within_days),
            )
        return statement

    @classmethod
    def _order_by(cls, sort: ListingSort) -> tuple[ColumnElement[Any], ...]:
        """`id` is always the last key so paging is stable when the primary key ties."""
        match sort:
            case ListingSort.DEADLINE:
                return (
                    nulls_last(TenderListing.submission_deadline.asc()),
                    TenderListing.id.asc(),
                )
            case ListingSort.NEWEST:
                return (
                    nulls_last(TenderListing.published_at.desc()),
                    TenderListing.created_at.desc(),
                    TenderListing.id.desc(),
                )
            case ListingSort.BUDGET_HIGH:
                return (nulls_last(cls._budget_ceiling().desc()), TenderListing.id.desc())
            case ListingSort.BUDGET_LOW:
                return (nulls_last(cls._budget_floor().asc()), TenderListing.id.asc())

    # ------------------------------------------------------------------
    # Public catalogue
    # ------------------------------------------------------------------

    async def list_public(
        self,
        filters: ListingFilters,
        *,
        limit: int,
        offset: int,
        now: datetime | None = None,
    ) -> tuple[list[TenderListing], int]:
        """One page of the public catalogue plus the unpaginated total."""
        base = select(TenderListing).where(self._published())
        base = self._apply_public_filters(base, filters, now=now or datetime.now(tz=UTC))

        total = int(
            (
                await self.session.execute(select(func.count()).select_from(base.subquery()))
            ).scalar_one()
        )
        rows = await self.session.execute(
            base.options(*self._card_options())
            .order_by(*self._order_by(filters.sort))
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars().unique().all()), total

    async def get_public(self, listing_id: uuid.UUID) -> TenderListing | None:
        """One published listing with its checklist and buyer. None for anything unpublished,
        which the API turns into 404 — a visitor learns nothing about a buyer's drafts."""
        result = await self.session.execute(
            select(TenderListing)
            .where(TenderListing.id == listing_id, self._published())
            .options(*self._card_options())
        )
        return result.scalar_one_or_none()

    async def category_counts(self) -> list[tuple[str, int]]:
        """Published-listing count per category, for categories that have at least one.

        Only non-empty categories come back. `GET /public/categories` must render all 30, but
        making SQL emit the zeros too — a generated series, or a left join against a values
        list of every enum member — is more machinery than a dict lookup in the service, which
        already holds the enum it needs to iterate.
        """
        result = await self.session.execute(
            select(TenderListing.category, func.count())
            .where(self._published())
            .group_by(TenderListing.category)
        )
        return [(category, int(count)) for category, count in result.all()]

    async def portal_stats(self) -> PortalStats:
        """The four hero counters in one pass over the published rows."""
        row = (
            (
                await self.session.execute(
                    select(
                        func.count().label("published_listings"),
                        func.count(func.distinct(TenderListing.organisation_id)).label("buyers"),
                        # Undisclosed budgets contribute nothing rather than distorting the total.
                        func.coalesce(func.sum(self._budget_ceiling()), 0).label("total_value"),
                        func.count(func.distinct(TenderListing.category)).label("categories"),
                    )
                    .select_from(TenderListing)
                    .where(self._published())
                )
            )
            .mappings()
            .one()
        )

        return PortalStats(
            published_listings=int(row["published_listings"]),
            buyer_organisations=int(row["buyers"]),
            total_value=Decimal(row["total_value"]),
            categories=int(row["categories"]),
        )

    async def candidates_for_search(
        self,
        *,
        categories: Sequence[TenderCategory] = (),
        emirates: Sequence[Emirate] = (),
        limit: int,
        now: datetime | None = None,
    ) -> list[TenderListing]:
        """The pool the deterministic ranker scores in Python (`docs/09` §5).

        SQL narrows by the interpreted categories and emirates and bounds the row count; it
        deliberately does no relevance ordering, because ranking is `app/domain`'s job and
        splitting it across two layers is how the two stop agreeing. An empty sequence means
        "the model inferred nothing here", which is a wider search, not an empty one.
        """
        statement = select(TenderListing).where(self._published())
        if categories:
            statement = statement.where(
                TenderListing.category.in_([category.value for category in categories])
            )
        if emirates:
            statement = statement.where(
                TenderListing.emirate.in_([emirate.value for emirate in emirates])
            )
        # Soonest-closing first so a truncated pool keeps the listings a bidder can still act on.
        statement = statement.where(
            or_(
                TenderListing.submission_deadline.is_(None),
                TenderListing.submission_deadline >= (now or datetime.now(tz=UTC)),
            )
        )
        rows = await self.session.execute(
            statement.options(*self._card_options())
            .order_by(nulls_last(TenderListing.submission_deadline.asc()), TenderListing.id)
            .limit(limit)
        )
        return list(rows.scalars().unique().all())

    # ------------------------------------------------------------------
    # Buyer-owned reads
    # ------------------------------------------------------------------

    async def list_for_owner(
        self,
        owner_user_id: uuid.UUID,
        *,
        status: ListingStatus | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[TenderListing], int]:
        base = select(TenderListing).where(self.owned_by(owner_user_id))
        if status is not None:
            base = base.where(TenderListing.status == status.value)

        total = int(
            (
                await self.session.execute(select(func.count()).select_from(base.subquery()))
            ).scalar_one()
        )
        rows = await self.session.execute(
            base.options(*self._card_options())
            .order_by(TenderListing.created_at.desc(), TenderListing.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars().unique().all()), total

    async def get_for_owner(
        self, listing_id: uuid.UUID, owner_user_id: uuid.UUID
    ) -> TenderListing | None:
        """One of the buyer's own listings, in any status, with its checklist loaded."""
        result = await self.session.execute(
            select(TenderListing)
            .where(TenderListing.id == listing_id, self.owned_by(owner_user_id))
            .options(*self._card_options())
        )
        return result.scalar_one_or_none()

    async def reference_exists(
        self,
        organisation_id: uuid.UUID,
        reference: str,
        *,
        exclude_listing_id: uuid.UUID | None = None,
    ) -> bool:
        """Pre-check for the per-organisation reference uniqueness constraint, so the API can
        answer 409 with a field name instead of letting an IntegrityError surface as a 500."""
        statement = select(TenderListing.id).where(
            TenderListing.organisation_id == organisation_id,
            TenderListing.reference == reference,
        )
        if exclude_listing_id is not None:
            statement = statement.where(TenderListing.id != exclude_listing_id)
        result = await self.session.execute(statement.limit(1))
        return result.scalar_one_or_none() is not None

    # ------------------------------------------------------------------
    # Denormalised counter
    # ------------------------------------------------------------------

    async def increment_application_count(self, listing_id: uuid.UUID) -> None:
        """Bump the card's applicant counter in the database, not in Python.

        Read-modify-write would lose a submission whenever two vendors submit inside the same
        window: both would read N and both would write N+1. `count = count + 1` is resolved by
        Postgres under the row lock the UPDATE already takes.
        """
        await self.session.execute(
            update(TenderListing)
            .where(TenderListing.id == listing_id)
            .values(application_count=TenderListing.application_count + 1)
        )

    async def decrement_application_count(self, listing_id: uuid.UUID) -> None:
        """Withdrawal's counterpart. `greatest(..., 0)` keeps the counter inside its CHECK
        constraint even if a withdrawal is somehow processed twice — a stuck-at-zero counter is
        a far better outcome than a failed request."""
        await self.session.execute(
            update(TenderListing)
            .where(TenderListing.id == listing_id)
            .values(
                application_count=func.greatest(TenderListing.application_count - 1, 0),
            )
        )

    async def list_due_for_closing(self, *, now: datetime | None = None) -> list[TenderListing]:
        """Published listings whose deadline has passed, for the scheduled close job."""
        result = await self.session.execute(
            select(TenderListing)
            .where(
                and_(
                    self._published(),
                    TenderListing.submission_deadline.is_not(None),
                    TenderListing.submission_deadline <= (now or datetime.now(tz=UTC)),
                )
            )
            .order_by(TenderListing.submission_deadline)
        )
        return list(result.scalars().all())
