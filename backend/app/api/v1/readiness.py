"""Readiness assessment read and human-override endpoints."""

from __future__ import annotations

import uuid
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Path

from app.api.dependencies import CurrentUser, ReadinessServiceDep
from app.api.errors import ProblemDetail
from app.schemas.readiness import ReadinessOverrideRequest, ReadinessRead

router = APIRouter(tags=["readiness"])

_OWNED: dict[int | str, dict[str, object]] = {
    HTTPStatus.UNAUTHORIZED: {"model": ProblemDetail},
    HTTPStatus.NOT_FOUND: {"model": ProblemDetail},
}

AnalysisId = Annotated[uuid.UUID, Path(description="Analysis identifier.")]


@router.get(
    "/analyses/{analysis_id}/readiness",
    response_model=ReadinessRead,
    summary="Get the readiness assessment",
    description=(
        "The deterministic score, per-dimension breakdown, hard blockers, and any override."
    ),
    responses=_OWNED,
)
async def get_readiness(
    analysis_id: AnalysisId, current_user: CurrentUser, service: ReadinessServiceDep
) -> ReadinessRead:
    assessment = await service.get(user_id=current_user.id, analysis_id=analysis_id)
    return ReadinessRead.from_model(assessment)


@router.patch(
    "/analyses/{analysis_id}/readiness/override",
    response_model=ReadinessRead,
    summary="Override the decision label",
    description=(
        "Human override. A reason is mandatory. The machine score and label are preserved; only "
        "the override is recorded."
    ),
    responses={**_OWNED, HTTPStatus.UNPROCESSABLE_ENTITY: {"model": ProblemDetail}},
)
async def override_readiness(
    analysis_id: AnalysisId,
    payload: ReadinessOverrideRequest,
    current_user: CurrentUser,
    service: ReadinessServiceDep,
) -> ReadinessRead:
    assessment = await service.override(
        user_id=current_user.id,
        analysis_id=analysis_id,
        decision_label=payload.decision_label.value,
        reason=payload.reason,
    )
    return ReadinessRead.from_model(assessment)
