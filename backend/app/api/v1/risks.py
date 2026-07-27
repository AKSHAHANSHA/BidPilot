"""Risk finding read and review endpoints."""

from __future__ import annotations

import uuid
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Path

from app.api.dependencies import CurrentUser, RiskServiceDep
from app.api.errors import ProblemDetail
from app.schemas.risk import ReviewRequest, RiskRead

router = APIRouter(tags=["risks"])

_OWNED: dict[int | str, dict[str, object]] = {
    HTTPStatus.UNAUTHORIZED: {"model": ProblemDetail},
    HTTPStatus.NOT_FOUND: {"model": ProblemDetail},
}

AnalysisId = Annotated[uuid.UUID, Path(description="Analysis identifier.")]
RiskId = Annotated[uuid.UUID, Path(description="Risk identifier.")]


@router.get(
    "/analyses/{analysis_id}/risks",
    response_model=list[RiskRead],
    summary="List an analysis's risk findings (most severe first)",
    responses=_OWNED,
)
async def list_risks(
    analysis_id: AnalysisId, current_user: CurrentUser, service: RiskServiceDep
) -> list[RiskRead]:
    risks = await service.list_for_analysis(user_id=current_user.id, analysis_id=analysis_id)
    return [RiskRead.model_validate(r) for r in risks]


@router.patch(
    "/risks/{risk_id}/review",
    response_model=RiskRead,
    summary="Record a human review of a risk",
    description="A reason is mandatory. The machine finding is preserved.",
    responses={**_OWNED, HTTPStatus.UNPROCESSABLE_ENTITY: {"model": ProblemDetail}},
)
async def review_risk(
    risk_id: RiskId,
    payload: ReviewRequest,
    current_user: CurrentUser,
    service: RiskServiceDep,
) -> RiskRead:
    risk = await service.review_risk(
        user_id=current_user.id,
        risk_id=risk_id,
        reviewed_status=payload.reviewed_status.value,
        reason=payload.reason,
    )
    return RiskRead.model_validate(risk)
