"""Company profile, evidence, and project endpoints.

**Route naming.** `docs/04_API_AND_DATA_MODEL.md` §3 already specifies `/company` and
`/company/evidence`, so these nest under `/company` rather than using flat `/company-profile`
and `/company-evidence` paths. The profile is a singleton per user, which a singular collection
path expresses correctly, and evidence and projects genuinely belong to it. `PATCH` supersedes
the `PUT` in that document because updates are partial.
"""

from __future__ import annotations

import uuid
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from app.api.dependencies import CompanyServiceDep, CurrentUser
from app.api.errors import ProblemDetail
from app.domain.enums import EvidenceCategory, ExpiryState, ProjectStatus, VerificationStatus
from app.models.company_evidence import CompanyEvidence
from app.models.company_profile import CompanyProfile
from app.models.company_project import CompanyProject
from app.repositories.company_repository import EvidenceFilters, ProjectFilters
from app.schemas.common import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT, Page
from app.schemas.company import (
    CompanyProfileCreate,
    CompanyProfileRead,
    CompanyProfileUpdate,
    CompletionRead,
)
from app.schemas.evidence import EvidenceCreate, EvidenceExpiry, EvidenceRead, EvidenceUpdate
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.services.company_service import CompanyService

router = APIRouter(prefix="/company", tags=["company"])

_OWNED_RESPONSES: dict[int | str, dict[str, object]] = {
    HTTPStatus.UNAUTHORIZED: {"model": ProblemDetail},
    HTTPStatus.NOT_FOUND: {"model": ProblemDetail},
}

EvidenceId = Annotated[uuid.UUID, Path(description="Evidence identifier.")]
ProjectId = Annotated[uuid.UUID, Path(description="Project identifier.")]
Limit = Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT, description="Rows per page.")]
Offset = Annotated[int, Query(ge=0, description="Rows to skip.")]


# --- Serialization helpers ------------------------------------------------------------------
# Kept in the route layer: turning a model plus a derived value into a response body is
# presentation, not policy.


def _profile_read(profile: CompanyProfile, service: CompanyService) -> CompanyProfileRead:
    completion = service.completion_for(profile)
    return CompanyProfileRead(
        id=str(profile.id),
        legal_name=profile.legal_name,
        trading_name=profile.trading_name,
        description=profile.description,
        industry=profile.industry,
        emirate=profile.emirate,
        country=profile.country,
        year_established=profile.year_established,
        employee_count=profile.employee_count,
        years_of_experience=profile.years_of_experience,
        trade_licence_number=profile.trade_licence_number,
        trade_licence_expiry=profile.trade_licence_expiry,
        licence_activities=list(profile.licence_activities),
        website=profile.website,
        contact_email=profile.contact_email,
        contact_phone=profile.contact_phone,
        annual_revenue_range=profile.annual_revenue_range,
        preferred_contract_value_min=profile.preferred_contract_value_min,
        preferred_contract_value_max=profile.preferred_contract_value_max,
        service_categories=list(profile.service_categories),
        geographic_coverage=list(profile.geographic_coverage),
        # The freshly calculated score, not the stored column.
        profile_completion_percentage=completion.score,
        completion=CompletionRead.from_result(completion),
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def _evidence_read(evidence: CompanyEvidence, service: CompanyService) -> EvidenceRead:
    expiry = service.expiry_for(evidence)
    return EvidenceRead(
        id=str(evidence.id),
        company_profile_id=str(evidence.company_profile_id),
        title=evidence.title,
        category=evidence.category,
        issuing_organisation=evidence.issuing_organisation,
        reference_number=evidence.reference_number,
        description=evidence.description,
        issue_date=evidence.issue_date,
        expiry_date=evidence.expiry_date,
        verification_status=evidence.verification_status,
        verification_notes=evidence.verification_notes,
        tags=list(evidence.tags),
        expiry=EvidenceExpiry(
            state=expiry.state,
            days_until_expiry=expiry.days_until_expiry,
            threshold_days=expiry.threshold_days,
        ),
        created_at=evidence.created_at,
        updated_at=evidence.updated_at,
    )


def _project_read(project: CompanyProject, service: CompanyService) -> ProjectRead:
    return ProjectRead(
        id=str(project.id),
        company_profile_id=str(project.company_profile_id),
        client_name=project.client_name,
        project_title=project.project_title,
        industry=project.industry,
        description=project.description,
        contract_value=project.contract_value,
        currency=project.currency,
        start_date=project.start_date,
        end_date=project.end_date,
        status=project.status,
        location=project.location,
        services_delivered=list(project.services_delivered),
        outcome=project.outcome,
        client_reference_available=project.client_reference_available,
        is_confidential=project.is_confidential,
        duration_months=service.duration_months_for(project),
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


# --- Profile --------------------------------------------------------------------------------


@router.post(
    "",
    response_model=CompanyProfileRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create the company profile",
    description=(
        "Each account may have exactly one company profile, enforced by a database unique "
        "constraint. A second attempt returns 409."
    ),
    responses={
        HTTPStatus.UNAUTHORIZED: {"model": ProblemDetail},
        HTTPStatus.CONFLICT: {"model": ProblemDetail},
    },
)
async def create_company_profile(
    payload: CompanyProfileCreate,
    current_user: CurrentUser,
    service: CompanyServiceDep,
) -> CompanyProfileRead:
    profile = await service.create_profile(user_id=current_user.id, payload=payload)
    return _profile_read(profile, service)


@router.get(
    "",
    response_model=CompanyProfileRead,
    summary="Get the company profile",
    description="Returns 404 until a profile has been created. Completion is calculated fresh.",
    responses=_OWNED_RESPONSES,
)
async def get_company_profile(
    current_user: CurrentUser, service: CompanyServiceDep
) -> CompanyProfileRead:
    profile = await service.get_profile(current_user.id)
    return _profile_read(profile, service)


@router.patch(
    "",
    response_model=CompanyProfileRead,
    summary="Update the company profile",
    description="Partial update. Omitted fields are left unchanged; completion is recalculated.",
    responses=_OWNED_RESPONSES,
)
async def update_company_profile(
    payload: CompanyProfileUpdate,
    current_user: CurrentUser,
    service: CompanyServiceDep,
) -> CompanyProfileRead:
    profile = await service.update_profile(user_id=current_user.id, payload=payload)
    return _profile_read(profile, service)


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete the company profile",
    description=(
        "Irreversible. Cascades to every evidence item and project belonging to the profile."
    ),
    responses=_OWNED_RESPONSES,
)
async def delete_company_profile(current_user: CurrentUser, service: CompanyServiceDep) -> None:
    await service.delete_profile(current_user.id)


# --- Evidence -------------------------------------------------------------------------------


@router.post(
    "/evidence",
    response_model=EvidenceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add company evidence",
    description=(
        "The evidence is attached to the caller's own profile; the profile ID is never taken "
        "from the request body. Requires an existing profile."
    ),
    responses={
        HTTPStatus.UNAUTHORIZED: {"model": ProblemDetail},
        HTTPStatus.UNPROCESSABLE_ENTITY: {"model": ProblemDetail},
    },
)
async def create_evidence(
    payload: EvidenceCreate,
    current_user: CurrentUser,
    service: CompanyServiceDep,
) -> EvidenceRead:
    evidence = await service.create_evidence(user_id=current_user.id, payload=payload)
    return _evidence_read(evidence, service)


@router.get(
    "/evidence",
    response_model=Page[EvidenceRead],
    summary="List company evidence",
    description=(
        "Offset-paginated and filterable. `expiry_state` filters on the derived state using the "
        "same rules as the detail response, evaluated in SQL."
    ),
    responses={HTTPStatus.UNAUTHORIZED: {"model": ProblemDetail}},
)
async def list_evidence(
    current_user: CurrentUser,
    service: CompanyServiceDep,
    category: Annotated[EvidenceCategory | None, Query()] = None,
    verification_status: Annotated[VerificationStatus | None, Query()] = None,
    expiry_state: Annotated[ExpiryState | None, Query()] = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    tag: Annotated[str | None, Query(max_length=40)] = None,
    limit: Limit = DEFAULT_PAGE_LIMIT,
    offset: Offset = 0,
) -> Page[EvidenceRead]:
    items, total = await service.list_evidence(
        user_id=current_user.id,
        filters=EvidenceFilters(
            category=category,
            verification_status=verification_status,
            expiry_state=expiry_state,
            search=search,
            tag=tag,
        ),
        limit=limit,
        offset=offset,
    )
    return Page[EvidenceRead].build(
        [_evidence_read(item, service) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/evidence/{evidence_id}",
    response_model=EvidenceRead,
    summary="Get one evidence item",
    responses=_OWNED_RESPONSES,
)
async def get_evidence(
    evidence_id: EvidenceId,
    current_user: CurrentUser,
    service: CompanyServiceDep,
) -> EvidenceRead:
    evidence = await service.get_evidence(user_id=current_user.id, evidence_id=evidence_id)
    return _evidence_read(evidence, service)


@router.patch(
    "/evidence/{evidence_id}",
    response_model=EvidenceRead,
    summary="Update an evidence item",
    responses=_OWNED_RESPONSES,
)
async def update_evidence(
    evidence_id: EvidenceId,
    payload: EvidenceUpdate,
    current_user: CurrentUser,
    service: CompanyServiceDep,
) -> EvidenceRead:
    evidence = await service.update_evidence(
        user_id=current_user.id, evidence_id=evidence_id, payload=payload
    )
    return _evidence_read(evidence, service)


@router.delete(
    "/evidence/{evidence_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an evidence item",
    responses=_OWNED_RESPONSES,
)
async def delete_evidence(
    evidence_id: EvidenceId,
    current_user: CurrentUser,
    service: CompanyServiceDep,
) -> None:
    await service.delete_evidence(user_id=current_user.id, evidence_id=evidence_id)


# --- Projects -------------------------------------------------------------------------------


@router.post(
    "/projects",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a previous or current project",
    responses={
        HTTPStatus.UNAUTHORIZED: {"model": ProblemDetail},
        HTTPStatus.UNPROCESSABLE_ENTITY: {"model": ProblemDetail},
    },
)
async def create_project(
    payload: ProjectCreate,
    current_user: CurrentUser,
    service: CompanyServiceDep,
) -> ProjectRead:
    project = await service.create_project(user_id=current_user.id, payload=payload)
    return _project_read(project, service)


@router.get(
    "/projects",
    response_model=Page[ProjectRead],
    summary="List projects",
    description="Offset-paginated, newest first by start date.",
    responses={HTTPStatus.UNAUTHORIZED: {"model": ProblemDetail}},
)
async def list_projects(
    current_user: CurrentUser,
    service: CompanyServiceDep,
    project_status: Annotated[ProjectStatus | None, Query(alias="status")] = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    service_filter: Annotated[str | None, Query(alias="service", max_length=120)] = None,
    limit: Limit = DEFAULT_PAGE_LIMIT,
    offset: Offset = 0,
) -> Page[ProjectRead]:
    items, total = await service.list_projects(
        user_id=current_user.id,
        filters=ProjectFilters(status=project_status, search=search, service=service_filter),
        limit=limit,
        offset=offset,
    )
    return Page[ProjectRead].build(
        [_project_read(item, service) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/projects/{project_id}",
    response_model=ProjectRead,
    summary="Get one project",
    responses=_OWNED_RESPONSES,
)
async def get_project(
    project_id: ProjectId,
    current_user: CurrentUser,
    service: CompanyServiceDep,
) -> ProjectRead:
    project = await service.get_project(user_id=current_user.id, project_id=project_id)
    return _project_read(project, service)


@router.patch(
    "/projects/{project_id}",
    response_model=ProjectRead,
    summary="Update a project",
    description=(
        "The status and end date must stay consistent: a current project has no end date, and a "
        "completed project requires one. Checked against stored values for partial updates."
    ),
    responses=_OWNED_RESPONSES,
)
async def update_project(
    project_id: ProjectId,
    payload: ProjectUpdate,
    current_user: CurrentUser,
    service: CompanyServiceDep,
) -> ProjectRead:
    project = await service.update_project(
        user_id=current_user.id, project_id=project_id, payload=payload
    )
    return _project_read(project, service)


@router.delete(
    "/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a project",
    responses=_OWNED_RESPONSES,
)
async def delete_project(
    project_id: ProjectId,
    current_user: CurrentUser,
    service: CompanyServiceDep,
) -> None:
    await service.delete_project(user_id=current_user.id, project_id=project_id)
