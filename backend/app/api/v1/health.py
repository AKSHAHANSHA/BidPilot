"""Liveness and readiness probes.

The split matters operationally: liveness answers "is this process alive?" and must never
depend on PostgreSQL or Redis, otherwise a brief database outage triggers a restart loop
that makes recovery slower. Readiness answers "should traffic be routed here?" and does
check dependencies.
"""

from __future__ import annotations

import asyncio
from http import HTTPStatus
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from starlette.responses import Response

from app.api.errors import ProblemDetail, problem_response
from app.core.database import check_database
from app.core.logging import get_logger
from app.core.redis_client import check_redis

logger = get_logger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


class LivenessResponse(BaseModel):
    status: Literal["live"] = "live"


class DependencyStatus(BaseModel):
    name: str = Field(examples=["database"])
    status: Literal["ok", "unavailable"]


class ReadinessResponse(BaseModel):
    status: Literal["ready", "degraded"]
    dependencies: list[DependencyStatus]


@router.get(
    "/live",
    response_model=LivenessResponse,
    summary="Liveness probe",
    description="Returns 200 whenever the process can serve requests. Checks no dependencies.",
)
async def liveness() -> LivenessResponse:
    return LivenessResponse()


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    description=(
        "Verifies PostgreSQL and Redis connectivity. Returns 503 problem+json naming the "
        "unavailable dependency when either check fails."
    ),
    responses={HTTPStatus.SERVICE_UNAVAILABLE: {"model": ProblemDetail}},
)
async def readiness(request: Request) -> ReadinessResponse | Response:
    checks = {"database": check_database(), "redis": check_redis()}
    outcomes = await asyncio.gather(*checks.values(), return_exceptions=True)

    dependencies: list[DependencyStatus] = []
    unavailable: list[str] = []
    for name, outcome in zip(checks, outcomes, strict=True):
        if isinstance(outcome, BaseException):
            # The underlying driver message can name hosts and credentials; log it, do not
            # return it.
            logger.warning(
                "readiness_dependency_unavailable",
                extra={"dependency": name, "error_type": type(outcome).__name__},
            )
            dependencies.append(DependencyStatus(name=name, status="unavailable"))
            unavailable.append(name)
        else:
            dependencies.append(DependencyStatus(name=name, status="ok"))

    if unavailable:
        return problem_response(
            status=HTTPStatus.SERVICE_UNAVAILABLE,
            code="SERVICE_DEPENDENCY_UNAVAILABLE",
            title="Service dependency unavailable",
            detail=f"Not ready: {', '.join(sorted(unavailable))} unavailable.",
            slug="service-unavailable",
            request=request,
        )

    return ReadinessResponse(status="ready", dependencies=dependencies)
