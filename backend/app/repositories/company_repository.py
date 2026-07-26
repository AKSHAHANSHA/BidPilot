"""Company profile, evidence, and project persistence.

All three extend the Phase 1 `OwnedRepository`, so the authenticated user ID is a required
argument of every read, list, and delete. No route re-implements an owner check.

Filtering is done in SQL rather than by loading rows and filtering in Python — including the
derived expiry state, whose predicates come from `app.domain.expiry` so the list endpoint and
the detail endpoint can never disagree about the same record.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any, cast

from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.sql.functions import concat

from app.domain.enums import EvidenceCategory, ExpiryState, ProjectStatus, VerificationStatus
from app.domain.expiry import expiry_state_filter
from app.models.company_evidence import CompanyEvidence
from app.models.company_profile import CompanyProfile
from app.models.company_project import CompanyProject
from app.repositories.base import OwnedRepository


class CompanyProfileRepository(OwnedRepository[CompanyProfile]):
    model = CompanyProfile
    owner_field = "owner_user_id"

    async def get_for_owner(self, user_id: uuid.UUID) -> CompanyProfile | None:
        """The user's single profile.

        A dedicated method rather than `list_for_user()[0]`: the one-profile-per-user rule is a
        unique constraint, so `scalar_one_or_none` correctly raises if that invariant is ever
        violated instead of silently picking a row.
        """
        result = await self.session.execute(select(CompanyProfile).where(self.owned_by(user_id)))
        return result.scalar_one_or_none()

    async def exists_for_owner(self, user_id: uuid.UUID) -> bool:
        result = await self.session.execute(select(CompanyProfile.id).where(self.owned_by(user_id)))
        return result.scalar_one_or_none() is not None


@dataclass(frozen=True, slots=True)
class EvidenceFilters:
    """Query parameters for the evidence list. All optional; all combine with AND."""

    category: EvidenceCategory | None = None
    verification_status: VerificationStatus | None = None
    expiry_state: ExpiryState | None = None
    search: str | None = None
    tag: str | None = None


class CompanyEvidenceRepository(OwnedRepository[CompanyEvidence]):
    model = CompanyEvidence
    owner_field = "owner_user_id"

    def _apply_filters(
        self,
        statement: Select[Any],
        filters: EvidenceFilters,
        *,
        today: date,
        threshold_days: int,
    ) -> Select[Any]:
        if filters.category is not None:
            statement = statement.where(CompanyEvidence.category == filters.category.value)

        if filters.verification_status is not None:
            statement = statement.where(
                CompanyEvidence.verification_status == filters.verification_status.value
            )

        if filters.expiry_state is not None:
            statement = statement.where(
                expiry_state_filter(
                    filters.expiry_state,
                    expiry_column=CompanyEvidence.expiry_date,
                    status_column=CompanyEvidence.verification_status,
                    today=today,
                    threshold_days=threshold_days,
                )
            )

        if filters.tag is not None:
            # Tags are stored normalized (trimmed, case-folded), so the filter normalizes too.
            statement = statement.where(
                CompanyEvidence.tags.contains([filters.tag.strip().casefold()])
            )

        if filters.search:
            statement = statement.where(self._search_predicate(filters.search))

        return statement

    @staticmethod
    def _search_predicate(term: str) -> ColumnElement[bool]:
        """Case-insensitive substring match across the user-facing text fields.

        `ILIKE` with an escaped term, not full-text search: the corpus is a handful of rows per
        user, and FTS would need a tsvector column plus a trigger for no practical gain here.
        Wildcards in the user's input are escaped so a search for "100%" is not a wildcard.
        """
        escaped = term.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = concat("%", escaped, "%")
        return or_(
            CompanyEvidence.title.ilike(pattern, escape="\\"),
            CompanyEvidence.description.ilike(pattern, escape="\\"),
            CompanyEvidence.issuing_organisation.ilike(pattern, escape="\\"),
            CompanyEvidence.reference_number.ilike(pattern, escape="\\"),
        )

    async def list_filtered(
        self,
        user_id: uuid.UUID,
        filters: EvidenceFilters,
        *,
        today: date,
        threshold_days: int,
        limit: int,
        offset: int,
    ) -> tuple[list[CompanyEvidence], int]:
        """One page of matching evidence plus the unpaginated total."""
        base = select(CompanyEvidence).where(self.owned_by(user_id))
        base = self._apply_filters(base, filters, today=today, threshold_days=threshold_days)

        count_statement = select(func.count()).select_from(base.subquery())
        total = int((await self.session.execute(count_statement)).scalar_one())

        page_statement = (
            base.order_by(CompanyEvidence.created_at.desc(), CompanyEvidence.id.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = await self.session.execute(page_statement)
        return list(rows.scalars().all()), total

    async def count_by_category(self, user_id: uuid.UUID) -> dict[str, int]:
        """Category histogram, used by the seed report and useful for a future dashboard."""
        result = await self.session.execute(
            select(CompanyEvidence.category, func.count())
            .where(self.owned_by(user_id))
            .group_by(CompanyEvidence.category)
        )
        return {category: int(count) for category, count in result.all()}


@dataclass(frozen=True, slots=True)
class ProjectFilters:
    status: ProjectStatus | None = None
    search: str | None = None
    service: str | None = None


class CompanyProjectRepository(OwnedRepository[CompanyProject]):
    model = CompanyProject
    owner_field = "owner_user_id"

    @staticmethod
    def _search_predicate(term: str) -> ColumnElement[bool]:
        escaped = term.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = concat("%", escaped, "%")
        return or_(
            CompanyProject.project_title.ilike(pattern, escape="\\"),
            CompanyProject.description.ilike(pattern, escape="\\"),
            CompanyProject.client_name.ilike(pattern, escape="\\"),
            CompanyProject.location.ilike(pattern, escape="\\"),
        )

    async def list_filtered(
        self,
        user_id: uuid.UUID,
        filters: ProjectFilters,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[CompanyProject], int]:
        base = select(CompanyProject).where(self.owned_by(user_id))

        if filters.status is not None:
            base = base.where(CompanyProject.status == filters.status.value)
        if filters.service is not None:
            base = base.where(CompanyProject.services_delivered.contains([filters.service]))
        if filters.search:
            base = base.where(self._search_predicate(filters.search))

        count_statement = select(func.count()).select_from(base.subquery())
        total = int((await self.session.execute(count_statement)).scalar_one())

        page_statement = (
            base.order_by(CompanyProject.start_date.desc(), CompanyProject.id.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = await self.session.execute(page_statement)
        return list(rows.scalars().all()), total

    async def count_for_profile(self, profile_id: uuid.UUID, user_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(CompanyProject)
            .where(
                CompanyProject.company_profile_id == profile_id,
                self.owned_by(user_id),
            )
        )
        return int(cast("Any", result).scalar_one())
