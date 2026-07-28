"""Persistence for marketplace projects, applications, and notifications.

Ownership rules:
- `MarketProjectRepository` — public reads use no ownership predicate (that is the whole
  point of `is_public`), but `list_for_company` and `get_for_company` require the poster's
  user id.
- `ApplicationRepository` — vendors see only their own applications; companies see the
  applications for projects they posted (join through `market_projects`).
- `NotificationRepository` — always scoped to `recipient_user_id`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import ColumnElement, func, or_, select, update
from sqlalchemy.sql.functions import concat

from app.domain.enums import ApplicationStatus, MarketProjectStatus
from app.models.application import Application
from app.models.market_project import MarketProject
from app.models.notification import Notification
from app.repositories.base import BaseRepository


@dataclass(frozen=True, slots=True)
class ProjectFilters:
    category: str | None = None
    search: str | None = None
    budget_min: Decimal | None = None
    budget_max: Decimal | None = None
    status: MarketProjectStatus | None = None
    only_public: bool = True


class MarketProjectRepository(BaseRepository[MarketProject]):
    model = MarketProject

    @staticmethod
    def _search_predicate(term: str) -> ColumnElement[bool]:
        escaped = term.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = concat("%", escaped, "%")
        return or_(
            MarketProject.title.ilike(pattern, escape="\\"),
            MarketProject.description.ilike(pattern, escape="\\"),
            MarketProject.company_display_name.ilike(pattern, escape="\\"),
            MarketProject.category.ilike(pattern, escape="\\"),
        )

    def _apply_filters(self, base, filters: ProjectFilters):
        if filters.only_public:
            base = base.where(MarketProject.is_public.is_(True))
        if filters.category:
            base = base.where(MarketProject.category == filters.category)
        if filters.search:
            base = base.where(self._search_predicate(filters.search))
        if filters.budget_min is not None:
            base = base.where(MarketProject.budget_aed >= filters.budget_min)
        if filters.budget_max is not None:
            base = base.where(MarketProject.budget_aed <= filters.budget_max)
        if filters.status is not None:
            base = base.where(MarketProject.status == filters.status.value)
        return base

    async def list_public(
        self, filters: ProjectFilters, *, limit: int, offset: int
    ) -> tuple[list[MarketProject], int]:
        base = self._apply_filters(select(MarketProject), filters)
        total = int(
            (
                await self.session.execute(
                    select(func.count()).select_from(base.subquery())
                )
            ).scalar_one()
        )
        rows = await self.session.execute(
            base.order_by(MarketProject.created_at.desc(), MarketProject.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars().all()), total

    async def get_public(self, project_id: uuid.UUID) -> MarketProject | None:
        result = await self.session.execute(
            select(MarketProject).where(
                MarketProject.id == project_id, MarketProject.is_public.is_(True)
            )
        )
        return result.scalar_one_or_none()

    async def get(self, project_id: uuid.UUID) -> MarketProject | None:
        result = await self.session.execute(
            select(MarketProject).where(MarketProject.id == project_id)
        )
        return result.scalar_one_or_none()

    async def list_for_company(self, company_id: uuid.UUID) -> list[MarketProject]:
        result = await self.session.execute(
            select(MarketProject)
            .where(MarketProject.posted_by_user_id == company_id)
            .order_by(MarketProject.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_for_company(
        self, project_id: uuid.UUID, company_id: uuid.UUID
    ) -> MarketProject | None:
        result = await self.session.execute(
            select(MarketProject).where(
                MarketProject.id == project_id,
                MarketProject.posted_by_user_id == company_id,
            )
        )
        return result.scalar_one_or_none()


class ApplicationRepository(BaseRepository[Application]):
    model = Application

    async def get_for_vendor(
        self, application_id: uuid.UUID, vendor_id: uuid.UUID
    ) -> Application | None:
        result = await self.session.execute(
            select(Application).where(
                Application.id == application_id,
                Application.vendor_user_id == vendor_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_existing(
        self, project_id: uuid.UUID, vendor_id: uuid.UUID
    ) -> Application | None:
        result = await self.session.execute(
            select(Application).where(
                Application.project_id == project_id,
                Application.vendor_user_id == vendor_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_vendor(self, vendor_id: uuid.UUID) -> list[Application]:
        result = await self.session.execute(
            select(Application)
            .where(Application.vendor_user_id == vendor_id)
            .order_by(Application.submitted_at.desc())
        )
        return list(result.scalars().all())

    async def list_for_project_by_company(
        self, project_id: uuid.UUID, company_id: uuid.UUID
    ) -> list[Application]:
        # Join through MarketProject so a company user only sees applicants to projects
        # they themselves posted.
        result = await self.session.execute(
            select(Application)
            .join(MarketProject, Application.project_id == MarketProject.id)
            .where(
                Application.project_id == project_id,
                MarketProject.posted_by_user_id == company_id,
            )
            .order_by(Application.ai_score.desc().nullslast(), Application.submitted_at.desc())
        )
        return list(result.scalars().all())

    async def get_for_company(
        self, application_id: uuid.UUID, company_id: uuid.UUID
    ) -> Application | None:
        # Joined through market_projects so the company user can only reach applications on
        # projects they themselves posted.
        result = await self.session.execute(
            select(Application)
            .join(MarketProject, Application.project_id == MarketProject.id)
            .where(
                Application.id == application_id,
                MarketProject.posted_by_user_id == company_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_recent_for_company(
        self, company_id: uuid.UUID, *, limit: int = 20
    ) -> list[Application]:
        result = await self.session.execute(
            select(Application)
            .join(MarketProject, Application.project_id == MarketProject.id)
            .where(MarketProject.posted_by_user_id == company_id)
            .order_by(Application.submitted_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def vendor_summary(self, vendor_id: uuid.UUID) -> dict[str, int | float | None]:
        rows = (
            await self.session.execute(
                select(Application.status, func.count(), func.avg(Application.ai_score))
                .where(Application.vendor_user_id == vendor_id)
                .group_by(Application.status)
            )
        ).all()
        counts = {status.value: 0 for status in ApplicationStatus}
        total = 0
        scores: list[float] = []
        for status, count, avg in rows:
            counts[str(status)] = int(count)
            total += int(count)
            if avg is not None:
                scores.append(float(avg))
        average = round(sum(scores) / len(scores), 1) if scores else None
        return {"total": total, "average": average, **counts}

    async def company_summary(self, company_id: uuid.UUID) -> dict[str, int | float | None]:
        # Total applicants and average score across all projects the company posted.
        total_result = await self.session.execute(
            select(func.count(), func.avg(Application.ai_score))
            .select_from(Application)
            .join(MarketProject, Application.project_id == MarketProject.id)
            .where(MarketProject.posted_by_user_id == company_id)
        )
        total, avg = total_result.one()
        return {
            "total_applicants": int(total or 0),
            "average_applicant_score": (
                round(float(avg), 1) if avg is not None else None
            ),
        }


class NotificationRepository(BaseRepository[Notification]):
    model = Notification

    async def list_for_user(
        self, user_id: uuid.UUID, *, limit: int = 50
    ) -> list[Notification]:
        result = await self.session.execute(
            select(Notification)
            .where(Notification.recipient_user_id == user_id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def counts_for_user(self, user_id: uuid.UUID) -> tuple[int, int]:
        total_row = await self.session.execute(
            select(func.count()).where(Notification.recipient_user_id == user_id)
        )
        unread_row = await self.session.execute(
            select(func.count()).where(
                Notification.recipient_user_id == user_id,
                Notification.read_at.is_(None),
            )
        )
        return int(unread_row.scalar_one()), int(total_row.scalar_one())

    async def mark_read(self, user_id: uuid.UUID, notification_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            update(Notification)
            .where(
                Notification.id == notification_id,
                Notification.recipient_user_id == user_id,
                Notification.read_at.is_(None),
            )
            .values(read_at=datetime.now(tz=UTC))
        )
        return bool(result.rowcount)

    async def mark_all_read(self, user_id: uuid.UUID) -> int:
        result = await self.session.execute(
            update(Notification)
            .where(
                Notification.recipient_user_id == user_id,
                Notification.read_at.is_(None),
            )
            .values(read_at=datetime.now(tz=UTC))
        )
        return int(result.rowcount or 0)
