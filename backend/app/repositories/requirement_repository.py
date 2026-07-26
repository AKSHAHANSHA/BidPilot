"""Requirement persistence and filtered reads, ownership-enforced."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.domain.enums import ComplianceStatus, RequirementCategory, RequirementObligation
from app.models.requirement import Requirement
from app.repositories.base import OwnedRepository


@dataclass(frozen=True, slots=True)
class RequirementFilters:
    category: RequirementCategory | None = None
    obligation: RequirementObligation | None = None
    reviewed_status: ComplianceStatus | None = None
    citation_verified: bool | None = None


class RequirementRepository(OwnedRepository[Requirement]):
    model = Requirement
    owner_field = "owner_user_id"

    async def get_with_citations(
        self, requirement_id: uuid.UUID, user_id: uuid.UUID
    ) -> Requirement | None:
        result = await self.session.execute(
            select(Requirement)
            .where(Requirement.id == requirement_id, self.owned_by(user_id))
            .options(selectinload(Requirement.citations))
        )
        return result.scalar_one_or_none()

    async def list_for_analysis(
        self,
        analysis_id: uuid.UUID,
        user_id: uuid.UUID,
        filters: RequirementFilters,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[Requirement], int]:
        base = select(Requirement).where(
            Requirement.analysis_id == analysis_id, self.owned_by(user_id)
        )
        if filters.category is not None:
            base = base.where(Requirement.category == filters.category.value)
        if filters.obligation is not None:
            base = base.where(Requirement.obligation == filters.obligation.value)
        if filters.reviewed_status is not None:
            base = base.where(Requirement.reviewed_status == filters.reviewed_status.value)
        if filters.citation_verified is not None:
            base = base.where(Requirement.citation_verified == filters.citation_verified)

        total = int(
            (
                await self.session.execute(select(func.count()).select_from(base.subquery()))
            ).scalar_one()
        )
        rows = await self.session.execute(
            base.options(selectinload(Requirement.citations))
            .order_by(Requirement.created_at, Requirement.id)
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars().all()), total

    async def count_for_analysis(self, analysis_id: uuid.UUID, user_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(Requirement)
            .where(Requirement.analysis_id == analysis_id, self.owned_by(user_id))
        )
        return int(result.scalar_one())
