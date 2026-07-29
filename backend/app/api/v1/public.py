"""The unauthenticated marketplace surface (`docs/09_PORTAL_SPEC.md` §3.1).

Every route here is reachable anonymously, which is exactly why none of them declares
`CurrentUser`: a dependency that resolved a user "if there is one" would make the anonymous
path the untested one. The published-only restriction lives in the repository rather than in
these handlers, so a future caller cannot reach the catalogue query without it.

`status` is the one field these responses do not read straight off the row.
:func:`derive_display_status` reports a published listing whose deadline has passed as closed,
because it is — nothing more can be bid. Rewriting the column instead would make an
unauthenticated `GET` a write.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.api.dependencies import ListingServiceDep, SearchServiceDep
from app.api.errors import ProblemDetail
from app.domain.enums import Emirate, TenderCategory
from app.models.listing import TenderListing
from app.repositories.listing_repository import ListingFilters, ListingSort
from app.schemas.common import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT, Page
from app.schemas.listing import CategoryCount, ListingCard, ListingDetail, PortalStats
from app.schemas.search import SearchMatch, SearchRequest, SearchResponse
from app.services.listing_service import derive_display_status

router = APIRouter(prefix="/public", tags=["public"])

_NOT_FOUND: dict[int | str, dict[str, object]] = {
    HTTPStatus.NOT_FOUND: {"model": ProblemDetail},
}

ListingId = Annotated[uuid.UUID, Path(description="Listing identifier.")]
Limit = Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT, description="Rows per page.")]
Offset = Annotated[int, Query(ge=0, description="Rows to skip.")]

#: Bounded to fit `Numeric(14, 2)` — the same ceiling the listing budget columns carry, so an
#: out-of-range filter is a 422 rather than a database error.
MAX_BUDGET_FILTER = Decimal("99999999999.99")
BudgetFilter = Annotated[Decimal | None, Query(ge=0, le=MAX_BUDGET_FILTER)]


def _detail(listing: TenderListing) -> ListingDetail:
    """Serialize a listing, replacing the stored status with the derived one.

    `ListingDetail.status` comes from the ORM attribute, which still reads `published` for a
    tender whose deadline passed an hour ago. Substituted on the way out rather than fixed in
    the schema, because only the service knows the rule.
    """
    return ListingDetail.model_validate(listing).model_copy(
        update={"status": derive_display_status(listing)}
    )


@router.get(
    "/listings",
    response_model=Page[ListingCard],
    summary="Browse the published tender catalogue",
    description=(
        "Published listings only — drafts, cancelled, and closed tenders are never returned. "
        "All filters combine with AND. A budget filter is a range *overlap*: a listing quoting "
        "1M-3M matches a search for anything above 2M. Listings that disclose no budget are "
        "excluded from a budget-filtered search rather than presented as possible matches."
    ),
)
async def list_public_listings(
    service: ListingServiceDep,
    category: Annotated[TenderCategory | None, Query()] = None,
    emirate: Annotated[Emirate | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200, description="Free text.")] = None,
    budget_min: BudgetFilter = None,
    budget_max: BudgetFilter = None,
    closing_within_days: Annotated[int | None, Query(ge=1, le=365)] = None,
    sort: Annotated[ListingSort, Query()] = ListingSort.DEADLINE,
    limit: Limit = DEFAULT_PAGE_LIMIT,
    offset: Offset = 0,
) -> Page[ListingCard]:
    items, total = await service.list_public(
        filters=ListingFilters(
            category=category,
            emirate=emirate,
            q=q,
            budget_min=budget_min,
            budget_max=budget_max,
            closing_within_days=closing_within_days,
            sort=sort,
        ),
        limit=limit,
        offset=offset,
    )
    return Page[ListingCard].build(
        [ListingCard.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/listings/{listing_id}",
    response_model=ListingDetail,
    summary="Get one published listing",
    description=(
        "The full brief, the buyer's organisation, and the document checklist an applicant "
        "will be screened against. Anything not published is 404 — a visitor learns nothing "
        "about a buyer's drafts."
    ),
    responses=_NOT_FOUND,
)
async def get_public_listing(listing_id: ListingId, service: ListingServiceDep) -> ListingDetail:
    return _detail(await service.get_public(listing_id))


@router.get(
    "/categories",
    response_model=Page[CategoryCount],
    summary="The category taxonomy with live listing counts",
    description=(
        "Every category, busiest first. Categories with no published listings are still "
        "returned so the landing page can render the whole taxonomy without it flickering as "
        "listings close. The full set always fits in one page; there is nothing to page "
        "through."
    ),
)
async def list_categories(service: ListingServiceDep) -> Page[CategoryCount]:
    tallies = await service.category_counts()
    items = [CategoryCount(category=tally.category, count=tally.count) for tally in tallies]
    return Page[CategoryCount].build(items, total=len(items), limit=len(items), offset=0)


@router.get(
    "/stats",
    response_model=PortalStats,
    summary="Landing-page counters",
    description=(
        "Published listings only. `total_published_value` sums the disclosed budgets; a "
        "listing that names no budget contributes nothing rather than an estimate."
    ),
)
async def get_portal_stats(service: ListingServiceDep) -> PortalStats:
    stats = await service.portal_stats()
    return PortalStats(
        published_listings=stats.published_listings,
        buying_organisations=stats.buyer_organisations,
        total_published_value=stats.total_value,
        active_categories=stats.categories,
    )


@router.post(
    "/search",
    response_model=SearchResponse,
    summary="Match listings to a plain-language description",
    description=(
        "The query is untrusted evidence, never an instruction: it is passed to the model as "
        "user content between delimiters and never interpolated into a system prompt. The "
        "model returns only a structured interpretation — it never sees the listing set and "
        "never orders results, so it cannot invent a listing. Ranking is deterministic Python "
        "over that interpretation, which is echoed back so the user can correct it. With no "
        "model configured the interpretation is derived from plain text processing and "
        "`degraded` is true; search never pretends a model ran."
    ),
)
async def search_listings(payload: SearchRequest, service: SearchServiceDep) -> SearchResponse:
    result = await service.search(payload)
    return SearchResponse(
        interpretation=result.interpretation,
        matches=[
            SearchMatch(
                listing=ListingCard.model_validate(match.listing),
                score=match.score,
                reasons=list(match.reasons),
            )
            for match in result.matches
        ],
        degraded=result.degraded,
    )
