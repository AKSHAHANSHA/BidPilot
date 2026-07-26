"""Requirement read endpoints (`docs/04` §3). Review actions arrive with Phase 8/9."""

from __future__ import annotations

import uuid
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.api.dependencies import CurrentUser, RequirementServiceDep
from app.api.errors import ProblemDetail
from app.domain.enums import ComplianceStatus, RequirementCategory, RequirementObligation
from app.repositories.requirement_repository import RequirementFilters
from app.schemas.common import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT, Page
from app.schemas.requirement import RequirementRead

router = APIRouter(tags=["requirements"])

_OWNED: dict[int | str, dict[str, object]] = {
    HTTPStatus.UNAUTHORIZED: {"model": ProblemDetail},
    HTTPStatus.NOT_FOUND: {"model": ProblemDetail},
}

AnalysisId = Annotated[uuid.UUID, Path(description="Analysis identifier.")]
RequirementId = Annotated[uuid.UUID, Path(description="Requirement identifier.")]


@router.get(
    "/analyses/{analysis_id}/requirements",
    response_model=Page[RequirementRead],
    summary="List an analysis's requirements",
    responses=_OWNED,
)
async def list_requirements(
    analysis_id: AnalysisId,
    current_user: CurrentUser,
    service: RequirementServiceDep,
    category: Annotated[RequirementCategory | None, Query()] = None,
    obligation: Annotated[RequirementObligation | None, Query()] = None,
    reviewed_status: Annotated[ComplianceStatus | None, Query()] = None,
    citation_verified: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT)] = DEFAULT_PAGE_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[RequirementRead]:
    items, total = await service.list_requirements(
        user_id=current_user.id,
        analysis_id=analysis_id,
        filters=RequirementFilters(
            category=category,
            obligation=obligation,
            reviewed_status=reviewed_status,
            citation_verified=citation_verified,
        ),
        limit=limit,
        offset=offset,
    )
    return Page[RequirementRead].build(
        [RequirementRead.model_validate(r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/requirements/{requirement_id}",
    response_model=RequirementRead,
    summary="Get one requirement with its citations",
    responses=_OWNED,
)
async def get_requirement(
    requirement_id: RequirementId,
    current_user: CurrentUser,
    service: RequirementServiceDep,
) -> RequirementRead:
    requirement = await service.get_requirement(
        user_id=current_user.id, requirement_id=requirement_id
    )
    return RequirementRead.model_validate(requirement)
