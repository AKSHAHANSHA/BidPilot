"""Tender listings, from the buying organisation's side (`docs/09_PORTAL_SPEC.md` §3.3).

Every route here is `CurrentCompany`: a vendor reaching one is told 403, because the account's
side is the problem, not the resource. Within that, ownership is still enforced per row by the
service, which resolves a listing through an owner-scoped read and answers 404 — never 403 —
for another buyer's listing, so the API never confirms that a given listing id exists.

The public view of the same rows lives in `public.py` and is restricted to published listings.
"""

from __future__ import annotations

import uuid
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from app.api.dependencies import (
    ApplicationServiceDep,
    CurrentCompany,
    ListingServiceDep,
    NotificationServiceDep,
)
from app.api.errors import ProblemDetail
from app.domain.enums import ApplicationStatus, ListingStatus
from app.models.listing import TenderListing
from app.schemas.application import ApplicantRead
from app.schemas.common import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT, Page
from app.schemas.listing import (
    DocumentRequirementRead,
    ListingCreate,
    ListingDetail,
    ListingUpdate,
    RequirementChecklistWrite,
)
from app.services.listing_service import derive_display_status
from app.services.notification_service import ApplicantRef

router = APIRouter(tags=["listings"])

_OWNED: dict[int | str, dict[str, object]] = {
    HTTPStatus.UNAUTHORIZED: {"model": ProblemDetail},
    HTTPStatus.FORBIDDEN: {"model": ProblemDetail},
    HTTPStatus.NOT_FOUND: {"model": ProblemDetail},
}

ListingId = Annotated[uuid.UUID, Path(description="Listing identifier.")]
Limit = Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT, description="Rows per page.")]
Offset = Annotated[int, Query(ge=0, description="Rows to skip.")]


def _detail(listing: TenderListing) -> ListingDetail:
    """Serialize a listing with the derived status rather than the stored one.

    The column still reads `published` for a tender whose deadline has passed; the owner is
    shown the same truth a visitor is, that nothing more can be bid. `/close` still applies —
    it is the transition that makes the column agree.
    """
    return ListingDetail.model_validate(listing).model_copy(
        update={"status": derive_display_status(listing)}
    )


def _requirements(listing: TenderListing) -> list[DocumentRequirementRead]:
    return [
        DocumentRequirementRead.model_validate(requirement)
        for requirement in listing.document_requirements
    ]


# --- The listing record ---------------------------------------------------------------------


@router.post(
    "/listings",
    response_model=ListingDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create a draft listing",
    description=(
        "Always created as a draft: `status` and `published_at` belong to the publish "
        "transition, which can check that the listing is actually biddable. A `reference` "
        "already used by another of your listings returns 409."
    ),
    responses={
        HTTPStatus.UNAUTHORIZED: {"model": ProblemDetail},
        HTTPStatus.FORBIDDEN: {"model": ProblemDetail},
        HTTPStatus.CONFLICT: {"model": ProblemDetail},
        HTTPStatus.UNPROCESSABLE_ENTITY: {"model": ProblemDetail},
    },
)
async def create_listing(
    payload: ListingCreate, current_user: CurrentCompany, service: ListingServiceDep
) -> ListingDetail:
    listing = await service.create_listing(user_id=current_user.id, payload=payload)
    return _detail(listing)


@router.get(
    "/listings",
    response_model=Page[ListingDetail],
    summary="List your own listings",
    description="Every status including drafts, newest first. Filter with `status`.",
    responses={
        HTTPStatus.UNAUTHORIZED: {"model": ProblemDetail},
        HTTPStatus.FORBIDDEN: {"model": ProblemDetail},
    },
)
async def list_listings(
    current_user: CurrentCompany,
    service: ListingServiceDep,
    listing_status: Annotated[ListingStatus | None, Query(alias="status")] = None,
    limit: Limit = DEFAULT_PAGE_LIMIT,
    offset: Offset = 0,
) -> Page[ListingDetail]:
    items, total = await service.list_listings(
        user_id=current_user.id, status=listing_status, limit=limit, offset=offset
    )
    return Page[ListingDetail].build(
        [_detail(item) for item in items], total=total, limit=limit, offset=offset
    )


@router.get(
    "/listings/{listing_id}",
    response_model=ListingDetail,
    summary="Get one of your listings",
    responses=_OWNED,
)
async def get_listing(
    listing_id: ListingId, current_user: CurrentCompany, service: ListingServiceDep
) -> ListingDetail:
    return _detail(await service.get_listing(user_id=current_user.id, listing_id=listing_id))


@router.patch(
    "/listings/{listing_id}",
    response_model=ListingDetail,
    summary="Update a listing",
    description=(
        "Partial update, allowed while the listing is a draft or published. A closed, awarded, "
        "or cancelled listing returns 409: its terms are the ones applicants bid against. A "
        "published listing cannot lose its deadline or have it moved into the past — use "
        "`/close` for that, so the applicants are told."
    ),
    responses={
        **_OWNED,
        HTTPStatus.CONFLICT: {"model": ProblemDetail},
        HTTPStatus.UNPROCESSABLE_ENTITY: {"model": ProblemDetail},
    },
)
async def update_listing(
    listing_id: ListingId,
    payload: ListingUpdate,
    current_user: CurrentCompany,
    service: ListingServiceDep,
) -> ListingDetail:
    listing = await service.update_listing(
        user_id=current_user.id, listing_id=listing_id, payload=payload
    )
    return _detail(listing)


# --- Document checklist ---------------------------------------------------------------------


@router.put(
    "/listings/{listing_id}/requirements",
    response_model=list[DocumentRequirementRead],
    summary="Replace the document checklist",
    description=(
        "The body is a bare array and replaces the whole checklist — omitting an entry is how "
        "a requirement is removed. Position in the array is the display order. Refused with "
        "409 once any application has been submitted: those bids were screened against the "
        "current list, and their stored scores would silently start describing requirements "
        "the applicants were never given."
    ),
    responses={
        **_OWNED,
        HTTPStatus.CONFLICT: {"model": ProblemDetail},
        HTTPStatus.UNPROCESSABLE_ENTITY: {"model": ProblemDetail},
    },
)
async def replace_requirements(
    listing_id: ListingId,
    payload: RequirementChecklistWrite,
    current_user: CurrentCompany,
    service: ListingServiceDep,
) -> list[DocumentRequirementRead]:
    listing = await service.replace_requirements(
        user_id=current_user.id, listing_id=listing_id, items=payload.root
    )
    return _requirements(listing)


# --- Lifecycle ------------------------------------------------------------------------------


@router.post(
    "/listings/{listing_id}/publish",
    response_model=ListingDetail,
    summary="Publish a draft listing",
    description=(
        "Only a draft can be published. Every unmet precondition is reported in one message: "
        "a submission deadline in the future, a description to bid against, and at least one "
        "mandatory document requirement — without one, every applicant screens identically and "
        "the score ranks nothing."
    ),
    responses={
        **_OWNED,
        HTTPStatus.CONFLICT: {"model": ProblemDetail},
        HTTPStatus.UNPROCESSABLE_ENTITY: {"model": ProblemDetail},
    },
)
async def publish_listing(
    listing_id: ListingId, current_user: CurrentCompany, service: ListingServiceDep
) -> ListingDetail:
    return _detail(await service.publish(user_id=current_user.id, listing_id=listing_id))


@router.post(
    "/listings/{listing_id}/close",
    response_model=ListingDetail,
    summary="Close a published listing",
    description=(
        "Ends the bidding window and notifies every applicant who has not withdrawn. Only a "
        "published listing can be closed; one whose deadline has merely passed is still "
        "published in the record and this is the normal way to settle it."
    ),
    responses={**_OWNED, HTTPStatus.CONFLICT: {"model": ProblemDetail}},
)
async def close_listing(
    listing_id: ListingId,
    current_user: CurrentCompany,
    service: ListingServiceDep,
    notifications: NotificationServiceDep,
) -> ListingDetail:
    closure = await service.close(user_id=current_user.id, listing_id=listing_id)
    # Staged into this request's unit of work, so a rollback cannot leave vendors holding a
    # message about a listing that is still open. The two services are joined here rather than
    # inside `ListingService` only because the listing service does not own notifications; see
    # the handover note — this pairing belongs in one place, not in a handler.
    notifications.listing_closed(
        listing_id=closure.listing.id,
        listing_title=closure.listing.title,
        applicants=[
            ApplicantRef(vendor_user_id=notice.vendor_user_id, application_id=notice.application_id)
            for notice in closure.notices
        ],
    )
    return _detail(closure.listing)


# --- Applicants -----------------------------------------------------------------------------


@router.get(
    "/listings/{listing_id}/applications",
    response_model=Page[ApplicantRead],
    summary="List the applicants on one of your listings",
    description=(
        "Ranked by screening score, highest first, with unscored submissions last rather than "
        "sorted to the top as though an empty score were the best one. Drafts are never "
        "returned: an unsent bid is not an applicant. `estimated_cost` and the margin derived "
        "from it are vendor-private and absent from this shape by construction."
    ),
    responses=_OWNED,
)
async def list_applicants(
    listing_id: ListingId,
    current_user: CurrentCompany,
    service: ApplicationServiceDep,
    application_status: Annotated[ApplicationStatus | None, Query(alias="status")] = None,
    limit: Limit = DEFAULT_PAGE_LIMIT,
    offset: Offset = 0,
) -> Page[ApplicantRead]:
    items, total = await service.list_applicants(
        owner_user_id=current_user.id,
        listing_id=listing_id,
        status=application_status,
        limit=limit,
        offset=offset,
    )
    return Page[ApplicantRead].build(
        [ApplicantRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )
