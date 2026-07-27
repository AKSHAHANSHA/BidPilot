"""Requirement read orchestration, ownership-enforced."""

from __future__ import annotations

import uuid

from app.api.errors import NotFoundError
from app.models.requirement import Requirement
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.requirement_repository import RequirementFilters, RequirementRepository


class RequirementService:
    def __init__(
        self, *, requirements: RequirementRepository, analyses: AnalysisRepository
    ) -> None:
        self.requirements = requirements
        self.analyses = analyses

    async def list_requirements(
        self,
        *,
        user_id: uuid.UUID,
        analysis_id: uuid.UUID,
        filters: RequirementFilters,
        limit: int,
        offset: int,
    ) -> tuple[list[Requirement], int]:
        # 404 for a foreign/absent analysis before listing, so the response cannot distinguish
        # "no requirements" from "not your analysis".
        analysis = await self.analyses.get_for_user(analysis_id, user_id)
        if analysis is None:
            raise NotFoundError("Analysis not found.")
        return await self.requirements.list_for_analysis(
            analysis_id, user_id, filters, limit=limit, offset=offset
        )

    async def get_requirement(
        self, *, user_id: uuid.UUID, requirement_id: uuid.UUID
    ) -> Requirement:
        requirement = await self.requirements.get_with_citations(requirement_id, user_id)
        if requirement is None:
            raise NotFoundError("Requirement not found.")
        return requirement

    async def review_requirement(
        self,
        *,
        user_id: uuid.UUID,
        requirement_id: uuid.UUID,
        reviewed_status: str,
        reason: str,
    ) -> Requirement:
        """Apply a human override. The original machine_status is preserved (`docs/03` §11)."""
        requirement = await self.get_requirement(user_id=user_id, requirement_id=requirement_id)
        requirement.reviewed_status = reviewed_status
        requirement.review_reason = reason
        await self.requirements.flush()
        return requirement
