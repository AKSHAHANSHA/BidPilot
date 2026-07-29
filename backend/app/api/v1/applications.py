"""Applications — a vendor's bid, and the buyer's verdict on it.

Two audiences share the `/applications` path and never share a route. Vendor routes declare
`CurrentVendor` and resolve the row by `vendor_user_id`; the two buyer routes declare
`CurrentCompany` and resolve it through the listing's owner. Neither lookup takes an
application id alone, so there is no handler here that could reach a row it has not proved the
caller owns — and a foreign application is 404, never 403, so its existence is never confirmed.

The two response shapes are not related by inheritance, deliberately: `ApplicationRead` carries
`estimated_cost` and the margin derived from it, and `ApplicantRead` is a separate class with
neither, so no field added to the vendor's view can ever reach the buyer they are bidding
against (`docs/09_PORTAL_SPEC.md` §10 rule 8).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Form, Path, Query, UploadFile, status
from pydantic import BaseModel, ConfigDict

from app.api.dependencies import (
    ApplicationServiceDep,
    CurrentCompany,
    CurrentVendor,
    ScreeningServiceDep,
)
from app.api.errors import ProblemDetail
from app.domain.enums import ApplicationStatus, RequiredDocumentType
from app.schemas.application import (
    ApplicantRead,
    ApplicationCreate,
    ApplicationDecision,
    ApplicationDocumentRead,
    ApplicationRead,
    ApplicationUpdate,
    VendorStats,
)
from app.schemas.common import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT, Page
from app.schemas.listing import ListingCard
from app.schemas.screening import ScreeningRead, ScreeningSummary

router = APIRouter(tags=["applications"])

_OWNED: dict[int | str, dict[str, object]] = {
    HTTPStatus.UNAUTHORIZED: {"model": ProblemDetail},
    HTTPStatus.FORBIDDEN: {"model": ProblemDetail},
    HTTPStatus.NOT_FOUND: {"model": ProblemDetail},
}

ApplicationId = Annotated[uuid.UUID, Path(description="Application identifier.")]
DocumentId = Annotated[uuid.UUID, Path(description="Application document identifier.")]
Limit = Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT, description="Rows per page.")]
Offset = Annotated[int, Query(ge=0, description="Rows to skip.")]


class ApplicationSummary(BaseModel):
    """One row of the vendor's application list.

    Everything `ApplicationRead` has except the attached documents, which the list query does
    not load — reading them here would emit one query per row, and a page of twenty-five bids
    does not need twenty-five file listings to render.

    Declared here rather than in `app/schemas/application.py` only because that module is
    owned elsewhere; it belongs beside its sibling shapes. Whoever moves it may instead delete
    it and use `ApplicationRead`, provided `ApplicationRepository.list_for_vendor` starts
    eager-loading `Application.documents` — today it does not, and serialising `ApplicationRead`
    from that query fails at read time rather than at import time.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    listing_id: uuid.UUID
    listing: ListingCard
    status: ApplicationStatus
    cover_letter: str | None
    bid_amount: Decimal | None
    estimated_cost: Decimal | None
    margin_amount: Decimal | None
    proposed_duration_months: int | None
    submitted_at: datetime | None
    decided_at: datetime | None
    withdrawn_at: datetime | None
    decision_note: str | None
    screening: ScreeningSummary | None
    created_at: datetime
    updated_at: datetime


# --- Vendor: the application record ----------------------------------------------------------


@router.post(
    "/applications",
    response_model=ApplicationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Start a draft application",
    description=(
        "Created against a published listing that is still accepting bids; anything else is a "
        "404 for an unpublished listing or a 409 for a closed one. One application per vendor "
        "per listing — a second attempt returns 409 naming the existing one."
    ),
    responses={
        **_OWNED,
        HTTPStatus.CONFLICT: {"model": ProblemDetail},
        HTTPStatus.UNPROCESSABLE_ENTITY: {"model": ProblemDetail},
    },
)
async def create_application(
    payload: ApplicationCreate, current_user: CurrentVendor, service: ApplicationServiceDep
) -> ApplicationRead:
    application = await service.create(vendor_user_id=current_user.id, payload=payload)
    return ApplicationRead.model_validate(application)


@router.get(
    "/applications",
    response_model=Page[ApplicationSummary],
    summary="List your own applications",
    description="Every status including your own drafts, newest first. Filter with `status`.",
    responses={
        HTTPStatus.UNAUTHORIZED: {"model": ProblemDetail},
        HTTPStatus.FORBIDDEN: {"model": ProblemDetail},
    },
)
async def list_applications(
    current_user: CurrentVendor,
    service: ApplicationServiceDep,
    application_status: Annotated[ApplicationStatus | None, Query(alias="status")] = None,
    limit: Limit = DEFAULT_PAGE_LIMIT,
    offset: Offset = 0,
) -> Page[ApplicationSummary]:
    items, total = await service.list_applications(
        vendor_user_id=current_user.id, status=application_status, limit=limit, offset=offset
    )
    return Page[ApplicationSummary].build(
        [ApplicationSummary.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# Declared before `/applications/{application_id}`: FastAPI matches in declaration order, and
# the other way round "stats" would be checked against a UUID path parameter and rejected as a
# malformed id rather than reaching this handler.
@router.get(
    "/applications/stats",
    response_model=VendorStats,
    summary="Vendor dashboard aggregates",
    description=(
        "Counts by status, a `waiting` roll-up of everything still awaiting a decision, and "
        "the money. Applications missing a figure are excluded from that figure and counted in "
        "`incomplete_financials`, so a partly-filled dashboard is visibly partial rather than "
        "quietly wrong. `margin_percentage` and `win_rate` are null — never zero — when their "
        "denominator is zero: a win rate over no decisions is unknown, not nil."
    ),
    responses={
        HTTPStatus.UNAUTHORIZED: {"model": ProblemDetail},
        HTTPStatus.FORBIDDEN: {"model": ProblemDetail},
    },
)
async def get_application_stats(
    current_user: CurrentVendor, service: ApplicationServiceDep
) -> VendorStats:
    return await service.stats(vendor_user_id=current_user.id)


@router.get(
    "/applications/{application_id}",
    response_model=ApplicationRead,
    summary="Get one of your applications",
    responses=_OWNED,
)
async def get_application(
    application_id: ApplicationId,
    current_user: CurrentVendor,
    service: ApplicationServiceDep,
) -> ApplicationRead:
    application = await service.get(vendor_user_id=current_user.id, application_id=application_id)
    return ApplicationRead.model_validate(application)


@router.patch(
    "/applications/{application_id}",
    response_model=ApplicationRead,
    summary="Edit a draft application",
    description=(
        "Drafts only. Once submitted the bid is what the buyer is reading, and editing it "
        "would make their applicant list a description of something that no longer exists."
    ),
    responses={**_OWNED, HTTPStatus.CONFLICT: {"model": ProblemDetail}},
)
async def update_application(
    application_id: ApplicationId,
    payload: ApplicationUpdate,
    current_user: CurrentVendor,
    service: ApplicationServiceDep,
) -> ApplicationRead:
    application = await service.update(
        vendor_user_id=current_user.id, application_id=application_id, payload=payload
    )
    return ApplicationRead.model_validate(application)


# --- Vendor: documents ------------------------------------------------------------------------


@router.post(
    "/applications/{application_id}/documents",
    response_model=ApplicationDocumentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Attach a PDF to a draft application",
    description=(
        "Multipart, one file per call, drafts only. The file must be a PDF by content (magic "
        "bytes), not just by name; size and page count are bounded; an identical file "
        "(SHA-256) already on this application returns 409. Storage paths are generated "
        "server-side — the client filename is display-only. `declared_document_type` is the "
        "vendor's own label and is a hint for screening, never a verdict: the pipeline still "
        "decides what the file actually is from its text."
    ),
    responses={
        **_OWNED,
        HTTPStatus.CONFLICT: {"model": ProblemDetail},
        HTTPStatus.REQUEST_ENTITY_TOO_LARGE: {"model": ProblemDetail},
        HTTPStatus.UNPROCESSABLE_ENTITY: {"model": ProblemDetail},
    },
)
async def upload_application_document(
    application_id: ApplicationId,
    file: UploadFile,
    current_user: CurrentVendor,
    service: ApplicationServiceDep,
    declared_document_type: Annotated[RequiredDocumentType | None, Form()] = None,
) -> ApplicationDocumentRead:
    content = await file.read()
    document = await service.upload_document(
        vendor_user_id=current_user.id,
        application_id=application_id,
        content=content,
        original_filename=file.filename,
        declared_document_type=declared_document_type,
    )
    return ApplicationDocumentRead.model_validate(document)


@router.delete(
    "/applications/{application_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a document from a draft application",
    responses={**_OWNED, HTTPStatus.CONFLICT: {"model": ProblemDetail}},
)
async def delete_application_document(
    application_id: ApplicationId,
    document_id: DocumentId,
    current_user: CurrentVendor,
    service: ApplicationServiceDep,
) -> None:
    await service.delete_document(
        vendor_user_id=current_user.id,
        application_id=application_id,
        document_id=document_id,
    )


# --- Vendor: lifecycle ------------------------------------------------------------------------


@router.post(
    "/applications/{application_id}/submit",
    response_model=ApplicationRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit the application and queue its screening",
    description=(
        "202 because a screening job is queued; poll `/applications/{id}/screening` for the "
        "real stage. At least one document is required — screening has nothing to assess "
        "otherwise — and the listing must still be open. Pressing submit twice changes "
        "nothing: the buyer is not told twice and the pipeline does not run twice. A screening "
        "that failed on our side can be re-run by submitting again, and that path is allowed "
        "even after the deadline, because re-running our own failure does not change the bid."
    ),
    responses={
        **_OWNED,
        HTTPStatus.CONFLICT: {"model": ProblemDetail},
        HTTPStatus.UNPROCESSABLE_ENTITY: {"model": ProblemDetail},
    },
)
async def submit_application(
    application_id: ApplicationId,
    current_user: CurrentVendor,
    service: ApplicationServiceDep,
) -> ApplicationRead:
    application, _enqueued = await service.submit(
        vendor_user_id=current_user.id, application_id=application_id
    )
    return ApplicationRead.model_validate(application)


@router.post(
    "/applications/{application_id}/withdraw",
    response_model=ApplicationRead,
    summary="Withdraw a submitted application",
    description=(
        "Idempotent. Refused for a draft, which was never sent, and after a decision, which is "
        "a matter of record. Withdrawing is final: the same listing cannot be applied to again."
    ),
    responses={**_OWNED, HTTPStatus.CONFLICT: {"model": ProblemDetail}},
)
async def withdraw_application(
    application_id: ApplicationId,
    current_user: CurrentVendor,
    service: ApplicationServiceDep,
) -> ApplicationRead:
    application = await service.withdraw(
        vendor_user_id=current_user.id, application_id=application_id
    )
    return ApplicationRead.model_validate(application)


@router.get(
    "/applications/{application_id}/screening",
    response_model=ScreeningRead,
    summary="Get the screening result for your application",
    description=(
        "Poll this while the status is `pending` or `processing`. There is no progress "
        "percentage: the status is the real pipeline stage, and a number nobody can check "
        "would be a fabrication. `overall_score` is computed in Python from the findings and "
        "is null until the run completes. Pages with no readable text that OCR could not "
        "recover are counted in `pages_needing_ocr` and reported as unreadable — never folded "
        "into `missing`, because the two need different things from you. 404 until the "
        "application has been submitted."
    ),
    responses=_OWNED,
)
async def get_application_screening(
    application_id: ApplicationId,
    current_user: CurrentVendor,
    service: ScreeningServiceDep,
) -> ScreeningRead:
    screening = await service.get_for_vendor(
        vendor_user_id=current_user.id, application_id=application_id
    )
    return ScreeningRead.model_validate(screening)


# --- Buyer ------------------------------------------------------------------------------------


@router.post(
    "/applications/{application_id}/review",
    response_model=ApplicantRead,
    summary="Mark an applicant as under review",
    description=(
        "Records that you have opened this application and moves it from `submitted` to "
        "`under_review`, which is what lets a vendor tell 'waiting for an answer' from 'nobody "
        "has looked yet'. The first-viewed timestamp is written once and never overwritten. No "
        "notification is sent: being read is not a decision, and a message for it would train "
        "vendors to ignore the ones that are."
    ),
    responses=_OWNED,
)
async def review_applicant(
    application_id: ApplicationId,
    current_user: CurrentCompany,
    service: ApplicationServiceDep,
) -> ApplicantRead:
    application = await service.mark_under_review(
        owner_user_id=current_user.id, application_id=application_id
    )
    return ApplicantRead.model_validate(application)


@router.patch(
    "/applications/{application_id}/decision",
    response_model=ApplicantRead,
    summary="Shortlist, approve, or reject an applicant",
    description=(
        "The vendor is notified, and your note is shown to them verbatim. A withdrawn "
        "application is no longer yours to judge, and an approval or rejection is not "
        "overwritten once the vendor has been told — both return 409."
    ),
    responses={**_OWNED, HTTPStatus.CONFLICT: {"model": ProblemDetail}},
)
async def decide_application(
    application_id: ApplicationId,
    payload: ApplicationDecision,
    current_user: CurrentCompany,
    service: ApplicationServiceDep,
) -> ApplicantRead:
    application = await service.decide(
        owner_user_id=current_user.id, application_id=application_id, payload=payload
    )
    return ApplicantRead.model_validate(application)
