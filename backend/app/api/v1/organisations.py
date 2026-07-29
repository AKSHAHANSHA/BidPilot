"""The signed-in account's own organisation.

**Route naming.** The path is singular — `/organisation`, not `/organisations/{id}` — for the
same reason `/company` is: an account has exactly one organisation, created with it at
registration, and a collection path would imply an id worth guessing. There is deliberately no
route that takes an organisation id: the row is always resolved from the authenticated user,
so "read or edit somebody else's organisation" is not a request this API can express.

Public and cross-account responses carry `OrganisationSummary` instead, which has no contact
block and no owner. `OrganisationRead` below is the owner's own view and appears nowhere else.
"""

from __future__ import annotations

from http import HTTPStatus

from fastapi import APIRouter

from app.api.dependencies import CurrentUser, OrganisationServiceDep
from app.api.errors import ProblemDetail
from app.schemas.organisation import OrganisationRead, OrganisationUpdate

router = APIRouter(prefix="/organisation", tags=["organisations"])

_OWNED: dict[int | str, dict[str, object]] = {
    HTTPStatus.UNAUTHORIZED: {"model": ProblemDetail},
    HTTPStatus.NOT_FOUND: {"model": ProblemDetail},
}


@router.get(
    "",
    response_model=OrganisationRead,
    summary="Get the signed-in account's organisation",
    description=(
        "Registration creates the organisation in the same transaction as the account, so a "
        "404 here means a pre-portal account rather than an ordinary empty state."
    ),
    responses=_OWNED,
)
async def get_organisation(
    current_user: CurrentUser, service: OrganisationServiceDep
) -> OrganisationRead:
    organisation = await service.get_own(current_user.id)
    return OrganisationRead.model_validate(organisation)


@router.patch(
    "",
    response_model=OrganisationRead,
    summary="Update the signed-in account's organisation",
    description=(
        "Partial update; omitted fields are left unchanged. `account_type` and `is_verified` "
        "are not editable — the first is fixed at registration and the second is set by an "
        "administrator out of band."
    ),
    responses={**_OWNED, HTTPStatus.UNPROCESSABLE_ENTITY: {"model": ProblemDetail}},
)
async def update_organisation(
    payload: OrganisationUpdate,
    current_user: CurrentUser,
    service: OrganisationServiceDep,
) -> OrganisationRead:
    organisation = await service.update_own(user_id=current_user.id, payload=payload)
    return OrganisationRead.model_validate(organisation)
