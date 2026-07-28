"""Marketplace orchestration.

Routes translate HTTP; this service does the work — creating projects, submitting
applications, and running the deterministic screening. Notification writes are inline
(no queue) because they are always fast row inserts and must happen in the same
transaction as the application state change that produced them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from app.api.errors import ConflictError, NotFoundError
from app.domain.enums import (
    AccountType,
    ApplicationStatus,
    MarketProjectStatus,
    NotificationKind,
)
from app.models.application import Application
from app.models.market_project import MarketProject
from app.models.notification import Notification
from app.models.user import User
from app.models.vendor_profile import VendorProfile
from app.repositories.marketplace_repository import (
    ApplicationRepository,
    MarketProjectRepository,
    NotificationRepository,
    ProjectFilters,
)
from app.schemas.marketplace import (
    ApplicationCreate,
    ApplicationReview,
    ProjectCreate,
    ProjectUpdate,
)
from app.services.screening import ScreeningInput, screen_application


@dataclass(frozen=True, slots=True)
class VendorSummary:
    stats: dict[str, int | float | None]
    recent: list[Application]


@dataclass(frozen=True, slots=True)
class CompanySummary:
    stats: dict[str, int | float | None]
    projects: list[MarketProject]
    recent_applications: list[Application]


class MarketplaceService:
    def __init__(
        self,
        *,
        projects: MarketProjectRepository,
        applications: ApplicationRepository,
        notifications: NotificationRepository,
    ) -> None:
        self.projects = projects
        self.applications = applications
        self.notifications = notifications

    # --- Public reads ------------------------------------------------------

    async def list_public(
        self, filters: ProjectFilters, *, limit: int, offset: int
    ) -> tuple[list[MarketProject], int]:
        return await self.projects.list_public(filters, limit=limit, offset=offset)

    async def get_public(self, project_id: uuid.UUID) -> MarketProject:
        project = await self.projects.get_public(project_id)
        if project is None:
            raise NotFoundError("Project not found")
        return project

    # --- Company writes ----------------------------------------------------

    async def create_project(self, *, company: User, payload: ProjectCreate) -> MarketProject:
        if company.account_type != AccountType.COMPANY.value:
            raise ConflictError("Only company accounts can post projects")

        project = MarketProject(
            posted_by_user_id=company.id,
            title=payload.title.strip(),
            company_display_name=company.display_name,
            description=payload.description.strip(),
            category=payload.category,
            location=payload.location,
            budget_aed=payload.budget_aed,
            submission_deadline=payload.submission_deadline,
            cover_image_url=payload.cover_image_url,
            requirements_summary=payload.requirements_summary,
            is_public=payload.is_public,
            status=MarketProjectStatus.OPEN.value,
        )
        self.projects.add(project)
        await self.projects.flush()
        return project

    async def update_project(
        self,
        *,
        company: User,
        project_id: uuid.UUID,
        payload: ProjectUpdate,
    ) -> MarketProject:
        project = await self.projects.get_for_company(project_id, company.id)
        if project is None:
            raise NotFoundError("Project not found")
        if payload.status is not None:
            project.status = payload.status.value
        if payload.is_public is not None:
            project.is_public = payload.is_public
        await self.projects.flush()
        return project

    async def list_company_projects(self, company_id: uuid.UUID) -> list[MarketProject]:
        return await self.projects.list_for_company(company_id)

    # --- Vendor applications ----------------------------------------------

    async def apply(
        self,
        *,
        vendor: User,
        vendor_profile: VendorProfile | None,
        payload: ApplicationCreate,
        document_storage_key: str | None = None,
        document_original_name: str | None = None,
    ) -> Application:
        if vendor.account_type != AccountType.VENDOR.value:
            raise ConflictError("Only vendor accounts can apply to projects")

        project = await self.projects.get(payload.project_id)
        if project is None or not project.is_public:
            raise NotFoundError("Project not found")

        existing = await self.applications.get_existing(project.id, vendor.id)
        if existing is not None:
            raise ConflictError("You have already applied to this project")

        screening = screen_application(
            ScreeningInput(
                project_title=project.title,
                project_description=project.description,
                project_category=project.category,
                project_requirements=project.requirements_summary,
                vendor_category=(vendor_profile.primary_category if vendor_profile else None),
                vendor_bio=vendor_profile.bio if vendor_profile else None,
                cover_letter=payload.cover_letter,
                document_original_name=document_original_name,
            )
        )
        now = datetime.now(tz=UTC)

        application = Application(
            project_id=project.id,
            vendor_user_id=vendor.id,
            document_storage_key=document_storage_key,
            document_original_name=document_original_name,
            ai_score=screening.score,
            ai_summary=screening.summary,
            ai_assessment=screening.breakdown,
            status=ApplicationStatus.SCREENED.value,
            submitted_at=now,
            reviewed_at=None,
        )
        self.applications.add(application)

        # Notify the company posting the project.
        self.notifications.add(
            Notification(
                recipient_user_id=project.posted_by_user_id,
                kind=NotificationKind.APPLICATION_SCREENED.value,
                title=f"New applicant for {project.title}",
                body=(
                    f"{vendor.display_name} applied with an AI screening score of "
                    f"{screening.score}/100."
                ),
                payload={
                    "project_id": str(project.id),
                    "score": screening.score,
                    "vendor_display_name": vendor.display_name,
                },
            )
        )
        await self.applications.flush()
        return application

    async def review_application(
        self,
        *,
        company: User,
        application_id: uuid.UUID,
        payload: ApplicationReview,
    ) -> Application:
        # A company user can only review applications on projects they posted; the repo helper
        # joins through market_projects so that check is a database-level filter.
        application_row = await self.applications.get_for_company(application_id, company.id)
        if application_row is None:
            raise NotFoundError("Application not found")

        application_row.status = payload.status.value
        application_row.review_note = payload.note
        application_row.reviewed_at = datetime.now(tz=UTC)

        # Notify the vendor that their status changed.
        self.notifications.add(
            Notification(
                recipient_user_id=application_row.vendor_user_id,
                kind=NotificationKind.APPLICATION_STATUS_CHANGED.value,
                title=f"Your application status is now: {payload.status.value}",
                body=payload.note,
                payload={
                    "application_id": str(application_row.id),
                    "project_id": str(application_row.project_id),
                    "status": payload.status.value,
                },
            )
        )
        await self.applications.flush()
        return application_row

    # --- Vendor dashboard --------------------------------------------------

    async def vendor_summary(self, vendor_id: uuid.UUID) -> VendorSummary:
        stats = await self.applications.vendor_summary(vendor_id)
        recent = await self.applications.list_for_vendor(vendor_id)
        return VendorSummary(stats=stats, recent=recent)

    async def company_summary(self, company_id: uuid.UUID) -> CompanySummary:
        projects = await self.projects.list_for_company(company_id)
        stats = await self.applications.company_summary(company_id)
        recent = await self.applications.list_recent_for_company(company_id)
        return CompanySummary(stats=stats, projects=projects, recent_applications=recent)

    # --- Notifications -----------------------------------------------------

    async def list_notifications(self, user_id: uuid.UUID) -> list[Notification]:
        return await self.notifications.list_for_user(user_id)

    async def notification_counts(self, user_id: uuid.UUID) -> tuple[int, int]:
        return await self.notifications.counts_for_user(user_id)

    async def mark_notification_read(self, user_id: uuid.UUID, notification_id: uuid.UUID) -> None:
        await self.notifications.mark_read(user_id, notification_id)

    async def mark_all_notifications_read(self, user_id: uuid.UUID) -> int:
        return await self.notifications.mark_all_read(user_id)


def coerce_decimal(value: str | None) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(value)
