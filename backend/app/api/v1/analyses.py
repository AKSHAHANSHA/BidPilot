"""Analysis endpoints: queue a run, read status, poll progress, retry."""

from __future__ import annotations

import uuid
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Path, Response, status

from app.api.dependencies import AnalysisServiceDep, CurrentUser
from app.api.errors import ProblemDetail
from app.schemas.analysis import AnalysisEvent, AnalysisRead

router = APIRouter(tags=["analyses"])

_OWNED: dict[int | str, dict[str, object]] = {
    HTTPStatus.UNAUTHORIZED: {"model": ProblemDetail},
    HTTPStatus.NOT_FOUND: {"model": ProblemDetail},
}

TenderId = Annotated[uuid.UUID, Path(description="Tender identifier.")]
AnalysisId = Annotated[uuid.UUID, Path(description="Analysis identifier.")]


def _read(analysis: object) -> AnalysisRead:
    read = AnalysisRead.model_validate(analysis)
    read.can_retry = analysis.can_retry  # type: ignore[attr-defined]
    return read


@router.post(
    "/tenders/{tender_id}/analyses",
    response_model=AnalysisRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue an analysis of the tender's latest document",
    description=(
        "Returns 202 with the queued analysis. If a run is already queued or processing, that "
        "run is returned instead of starting a duplicate. Requires an analysable document."
    ),
    responses={
        HTTPStatus.UNAUTHORIZED: {"model": ProblemDetail},
        HTTPStatus.NOT_FOUND: {"model": ProblemDetail},
        HTTPStatus.UNPROCESSABLE_ENTITY: {"model": ProblemDetail},
    },
)
async def create_analysis(
    tender_id: TenderId,
    response: Response,
    current_user: CurrentUser,
    service: AnalysisServiceDep,
) -> AnalysisRead:
    analysis, created = await service.create_analysis(user_id=current_user.id, tender_id=tender_id)
    if not created:
        response.status_code = status.HTTP_200_OK  # idempotent: existing run returned
    return _read(analysis)


@router.get(
    "/tenders/{tender_id}/analyses",
    response_model=list[AnalysisRead],
    summary="List a tender's analyses (newest version first)",
    responses=_OWNED,
)
async def list_analyses(
    tender_id: TenderId, current_user: CurrentUser, service: AnalysisServiceDep
) -> list[AnalysisRead]:
    analyses = await service.list_for_tender(user_id=current_user.id, tender_id=tender_id)
    return [_read(a) for a in analyses]


@router.get(
    "/analyses/{analysis_id}",
    response_model=AnalysisRead,
    summary="Get an analysis",
    responses=_OWNED,
)
async def get_analysis(
    analysis_id: AnalysisId, current_user: CurrentUser, service: AnalysisServiceDep
) -> AnalysisRead:
    analysis = await service.get_analysis(user_id=current_user.id, analysis_id=analysis_id)
    return _read(analysis)


@router.get(
    "/analyses/{analysis_id}/events",
    response_model=AnalysisEvent,
    summary="Poll analysis progress",
    description=(
        "A compact status snapshot for polling every 2-3 seconds. Real stages only — the "
        "backend never reports a fabricated percentage."
    ),
    responses=_OWNED,
)
async def analysis_events(
    analysis_id: AnalysisId, current_user: CurrentUser, service: AnalysisServiceDep
) -> AnalysisEvent:
    analysis = await service.get_analysis(user_id=current_user.id, analysis_id=analysis_id)
    event = AnalysisEvent.model_validate(analysis)
    event.can_retry = analysis.can_retry
    return event


@router.post(
    "/analyses/{analysis_id}/retry",
    response_model=AnalysisRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Retry a failed analysis",
    description="Re-queues a failed run in place, keeping its version and history.",
    responses={
        **_OWNED,
        HTTPStatus.CONFLICT: {"model": ProblemDetail},
    },
)
async def retry_analysis(
    analysis_id: AnalysisId, current_user: CurrentUser, service: AnalysisServiceDep
) -> AnalysisRead:
    analysis = await service.retry_analysis(user_id=current_user.id, analysis_id=analysis_id)
    return _read(analysis)
