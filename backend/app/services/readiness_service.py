"""Readiness read and override orchestration, ownership-enforced."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.api.errors import NotFoundError
from app.models.readiness import ReadinessAssessment
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.base import BaseRepository


class _ReadinessRepository(BaseRepository[ReadinessAssessment]):
    model = ReadinessAssessment


class ReadinessService:
    def __init__(self, *, session: object, analyses: AnalysisRepository) -> None:
        self.analyses = analyses
        self._repo = _ReadinessRepository(session)  # type: ignore[arg-type]

    async def get(self, *, user_id: uuid.UUID, analysis_id: uuid.UUID) -> ReadinessAssessment:
        # Ownership is enforced by the analysis lookup; the assessment shares its owner.
        analysis = await self.analyses.get_for_user(analysis_id, user_id)
        if analysis is None:
            raise NotFoundError("Analysis not found.")
        result = await self._repo.session.execute(
            select(ReadinessAssessment).where(
                ReadinessAssessment.analysis_id == analysis_id,
                ReadinessAssessment.owner_user_id == user_id,
            )
        )
        assessment = result.scalar_one_or_none()
        if assessment is None:
            raise NotFoundError("This analysis has no readiness assessment yet.")
        return assessment

    async def override(
        self,
        *,
        user_id: uuid.UUID,
        analysis_id: uuid.UUID,
        decision_label: str,
        reason: str,
    ) -> ReadinessAssessment:
        """Record a human override. The machine score and label are untouched."""
        assessment = await self.get(user_id=user_id, analysis_id=analysis_id)
        assessment.human_override_label = decision_label
        assessment.human_override_reason = reason
        await self._repo.flush()
        return assessment
