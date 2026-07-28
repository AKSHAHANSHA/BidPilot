"""Authenticated marketplace routes: company posts, vendor apps, notifications.

Company endpoints under `/company/*`, vendor endpoints under `/vendor/*`; each checks the
account_type of the caller and returns 409 when the role does not match, so a vendor
cannot post a project and a company cannot apply.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.dependencies import (
    CurrentUser,
    MarketplaceServiceDep,
    SessionDep,
)
from app.api.errors import ProblemDetail
from app.domain.enums import AccountType
from app.models.vendor_profile import VendorProfile
from app.schemas.marketplace import (
    ApplicationCreate,
    ApplicationDetail,
    ApplicationReview,
    ApplicationSummary,
    CompanyDashboardSummary,
    NotificationCounts,
    NotificationRead,
    ProjectCreate,
    ProjectDetail,
    ProjectSummary,
    ProjectUpdate,
    VendorDashboardSummary,
)

router = APIRouter(tags=["marketplace"])


_ROLE_MISMATCH: dict[int | str, dict[str, object]] = {
    status.HTTP_409_CONFLICT: {"model": ProblemDetail},
    status.HTTP_404_NOT_FOUND: {"model": ProblemDetail},
}


def _require(account_type: str, current: CurrentUser) -> None:
    if current.account_type != account_type:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This endpoint requires a {account_type} account.",
        )


# ---------------------------------------------------------------------------
# Company: post & manage projects
# ---------------------------------------------------------------------------


@router.post(
    "/company/projects",
    response_model=ProjectDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Post a new marketplace project (company only)",
    responses=_ROLE_MISMATCH,
)
async def company_create_project(
    payload: ProjectCreate,
    current_user: CurrentUser,
    marketplace: MarketplaceServiceDep,
) -> ProjectDetail:
    _require(AccountType.COMPANY.value, current_user)
    project = await marketplace.create_project(company=current_user, payload=payload)
    return ProjectDetail.model_validate(project)


@router.get(
    "/company/projects",
    response_model=list[ProjectSummary],
    summary="Projects posted by the signed-in company",
    responses=_ROLE_MISMATCH,
)
async def company_list_projects(
    current_user: CurrentUser, marketplace: MarketplaceServiceDep
) -> list[ProjectSummary]:
    _require(AccountType.COMPANY.value, current_user)
    projects = await marketplace.list_company_projects(current_user.id)
    return [ProjectSummary.model_validate(p) for p in projects]


@router.patch(
    "/company/projects/{project_id}",
    response_model=ProjectDetail,
    summary="Update a project's status or visibility",
    responses=_ROLE_MISMATCH,
)
async def company_update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    current_user: CurrentUser,
    marketplace: MarketplaceServiceDep,
) -> ProjectDetail:
    _require(AccountType.COMPANY.value, current_user)
    project = await marketplace.update_project(
        company=current_user, project_id=project_id, payload=payload
    )
    return ProjectDetail.model_validate(project)


@router.get(
    "/company/projects/{project_id}/applications",
    response_model=list[ApplicationSummary],
    summary="Applicants for a project the signed-in company posted",
    responses=_ROLE_MISMATCH,
)
async def company_list_applicants(
    project_id: uuid.UUID,
    current_user: CurrentUser,
    marketplace: MarketplaceServiceDep,
) -> list[ApplicationSummary]:
    _require(AccountType.COMPANY.value, current_user)
    rows = await marketplace.applications.list_for_project_by_company(
        project_id, current_user.id
    )
    return [ApplicationSummary.model_validate(r) for r in rows]


@router.patch(
    "/company/applications/{application_id}",
    response_model=ApplicationDetail,
    summary="Review an application (shortlist / reject)",
    responses=_ROLE_MISMATCH,
)
async def company_review_application(
    application_id: uuid.UUID,
    payload: ApplicationReview,
    current_user: CurrentUser,
    marketplace: MarketplaceServiceDep,
) -> ApplicationDetail:
    _require(AccountType.COMPANY.value, current_user)
    row = await marketplace.review_application(
        company=current_user, application_id=application_id, payload=payload
    )
    return ApplicationDetail.model_validate(row)


@router.get(
    "/company/dashboard/summary",
    response_model=CompanyDashboardSummary,
    summary="Aggregates for the company dashboard",
    responses=_ROLE_MISMATCH,
)
async def company_dashboard(
    current_user: CurrentUser, marketplace: MarketplaceServiceDep
) -> CompanyDashboardSummary:
    _require(AccountType.COMPANY.value, current_user)
    summary = await marketplace.company_summary(current_user.id)
    projects = summary["projects"]  # type: ignore[assignment]
    stats = summary["stats"]  # type: ignore[assignment]
    recent = summary["recent_applications"]  # type: ignore[assignment]
    open_count = sum(1 for p in projects if p.status == "open")
    return CompanyDashboardSummary(
        total_projects=len(projects),
        open_projects=open_count,
        total_applicants=int(stats.get("total_applicants", 0) or 0),
        average_applicant_score=stats.get("average_applicant_score"),
        recent_applications=[ApplicationSummary.model_validate(r) for r in recent],
    )


# ---------------------------------------------------------------------------
# Vendor: apply, dashboard
# ---------------------------------------------------------------------------


@router.post(
    "/vendor/applications",
    response_model=ApplicationDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Apply to a marketplace project (vendor only)",
    responses=_ROLE_MISMATCH,
)
async def vendor_apply(
    payload: ApplicationCreate,
    current_user: CurrentUser,
    marketplace: MarketplaceServiceDep,
    session: SessionDep,
) -> ApplicationDetail:
    _require(AccountType.VENDOR.value, current_user)
    profile_result = await session.execute(
        select(VendorProfile).where(VendorProfile.owner_user_id == current_user.id)
    )
    vendor_profile = profile_result.scalar_one_or_none()
    application = await marketplace.apply(
        vendor=current_user, vendor_profile=vendor_profile, payload=payload
    )
    return ApplicationDetail.model_validate(application)


@router.get(
    "/vendor/applications",
    response_model=list[ApplicationSummary],
    summary="Applications submitted by the signed-in vendor",
    responses=_ROLE_MISMATCH,
)
async def vendor_list_applications(
    current_user: CurrentUser, marketplace: MarketplaceServiceDep
) -> list[ApplicationSummary]:
    _require(AccountType.VENDOR.value, current_user)
    rows = await marketplace.applications.list_for_vendor(current_user.id)
    return [ApplicationSummary.model_validate(r) for r in rows]


@router.get(
    "/vendor/dashboard/summary",
    response_model=VendorDashboardSummary,
    summary="Aggregates for the vendor dashboard",
    responses=_ROLE_MISMATCH,
)
async def vendor_dashboard(
    current_user: CurrentUser, marketplace: MarketplaceServiceDep
) -> VendorDashboardSummary:
    _require(AccountType.VENDOR.value, current_user)
    result = await marketplace.vendor_summary(current_user.id)
    stats = result["stats"]  # type: ignore[assignment]
    recent = result["recent"]  # type: ignore[assignment]
    return VendorDashboardSummary(
        total_applications=int(stats.get("total", 0) or 0),
        submitted=int(stats.get("submitted", 0) or 0),
        screened=int(stats.get("screened", 0) or 0),
        shortlisted=int(stats.get("shortlisted", 0) or 0),
        rejected=int(stats.get("rejected", 0) or 0),
        average_ai_score=stats.get("average"),
        applications=[ApplicationSummary.model_validate(r) for r in recent],
    )


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


@router.get(
    "/notifications",
    response_model=list[NotificationRead],
    summary="Notifications for the signed-in user",
)
async def list_notifications(
    current_user: CurrentUser, marketplace: MarketplaceServiceDep
) -> list[NotificationRead]:
    rows = await marketplace.list_notifications(current_user.id)
    return [NotificationRead.model_validate(r) for r in rows]


@router.get(
    "/notifications/counts",
    response_model=NotificationCounts,
    summary="Unread/total notification counts",
)
async def notification_counts(
    current_user: CurrentUser, marketplace: MarketplaceServiceDep
) -> NotificationCounts:
    unread, total = await marketplace.notification_counts(current_user.id)
    return NotificationCounts(unread=unread, total=total)


@router.patch(
    "/notifications/{notification_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark a notification read",
)
async def mark_notification_read(
    notification_id: uuid.UUID,
    current_user: CurrentUser,
    marketplace: MarketplaceServiceDep,
) -> None:
    await marketplace.mark_notification_read(current_user.id, notification_id)


@router.patch(
    "/notifications/read-all",
    summary="Mark every notification read",
)
async def mark_all_notifications_read(
    current_user: CurrentUser, marketplace: MarketplaceServiceDep
) -> dict[str, int]:
    updated = await marketplace.mark_all_notifications_read(current_user.id)
    return {"updated": updated}
