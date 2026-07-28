"""Public marketplace routes.

No authentication. Only exposes marketplace projects with `is_public=true`. Never exposes
applicant identities or internal state.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Query

from app.api.dependencies import MarketplaceServiceDep
from app.domain.categories import PROJECT_CATEGORIES
from app.domain.enums import MarketProjectStatus
from app.repositories.marketplace_repository import ProjectFilters
from app.schemas.marketplace import (
    CategoryRead,
    ProjectDetail,
    ProjectListResponse,
    ProjectSearchRequest,
    ProjectSummary,
)

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/categories", response_model=list[CategoryRead], summary="Marketplace categories")
async def list_categories() -> list[CategoryRead]:
    return [CategoryRead(slug=c.slug, label=c.label, icon=c.icon) for c in PROJECT_CATEGORIES]


@router.get(
    "/projects",
    response_model=ProjectListResponse,
    summary="Browse public marketplace projects",
)
async def list_projects(
    marketplace: MarketplaceServiceDep,
    category: str | None = Query(default=None, max_length=80),
    q: str | None = Query(default=None, max_length=500),
    budget_min: Decimal | None = Query(default=None, ge=0),
    budget_max: Decimal | None = Query(default=None, ge=0),
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ProjectListResponse:
    filters = ProjectFilters(
        category=category,
        search=q,
        budget_min=budget_min,
        budget_max=budget_max,
        status=MarketProjectStatus.OPEN,
        only_public=True,
    )
    items, total = await marketplace.list_public(filters, limit=limit, offset=offset)
    return ProjectListResponse(
        items=[ProjectSummary.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/projects/{project_id}",
    response_model=ProjectDetail,
    summary="Public project detail",
)
async def get_project(project_id: str, marketplace: MarketplaceServiceDep) -> ProjectDetail:
    import uuid as _uuid

    project = await marketplace.get_public(_uuid.UUID(project_id))
    return ProjectDetail.model_validate(project)


@router.post(
    "/projects/search",
    response_model=ProjectListResponse,
    summary="Free-text search over the marketplace",
    description=(
        "Ranked token-overlap search across title, description, category, and company name. "
        "No LLM call — deterministic and free. Wired to the landing page's chat-style input."
    ),
)
async def search_projects(
    payload: ProjectSearchRequest, marketplace: MarketplaceServiceDep
) -> ProjectListResponse:
    filters = ProjectFilters(
        search=payload.query,
        status=MarketProjectStatus.OPEN,
        only_public=True,
    )
    items, total = await marketplace.list_public(filters, limit=payload.limit, offset=0)
    return ProjectListResponse(
        items=[ProjectSummary.model_validate(item) for item in items],
        total=total,
        limit=payload.limit,
        offset=0,
    )
