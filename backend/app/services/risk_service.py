"""Risk read and review orchestration, ownership-enforced."""

from __future__ import annotations

import uuid

from app.api.errors import NotFoundError
from app.models.risk import RiskFinding
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.risk_repository import RiskRepository


class RiskService:
    def __init__(self, *, risks: RiskRepository, analyses: AnalysisRepository) -> None:
        self.risks = risks
        self.analyses = analyses

    async def list_for_analysis(
        self, *, user_id: uuid.UUID, analysis_id: uuid.UUID
    ) -> list[RiskFinding]:
        analysis = await self.analyses.get_for_user(analysis_id, user_id)
        if analysis is None:
            raise NotFoundError("Analysis not found.")
        return await self.risks.list_for_analysis(analysis_id, user_id)

    async def review_risk(
        self, *, user_id: uuid.UUID, risk_id: uuid.UUID, reviewed_status: str, reason: str
    ) -> RiskFinding:
        risk = await self.risks.get_with_citations(risk_id, user_id)
        if risk is None:
            raise NotFoundError("Risk not found.")
        risk.reviewed_status = reviewed_status
        risk.review_reason = reason
        await self.risks.flush()
        return risk
