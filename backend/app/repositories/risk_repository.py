"""Risk finding persistence, ownership-enforced."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.risk import RiskFinding
from app.repositories.base import OwnedRepository

#: Severity ordering for a sensible default sort (most serious first).
_SEVERITY_ORDER = (
    "CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 "
    "WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END"
)


class RiskRepository(OwnedRepository[RiskFinding]):
    model = RiskFinding
    owner_field = "owner_user_id"

    async def list_for_analysis(
        self, analysis_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[RiskFinding]:
        from sqlalchemy import text

        result = await self.session.execute(
            select(RiskFinding)
            .where(RiskFinding.analysis_id == analysis_id, self.owned_by(user_id))
            .options(selectinload(RiskFinding.citations))
            .order_by(text(_SEVERITY_ORDER), RiskFinding.created_at)
        )
        return list(result.scalars().all())

    async def get_with_citations(
        self, risk_id: uuid.UUID, user_id: uuid.UUID
    ) -> RiskFinding | None:
        result = await self.session.execute(
            select(RiskFinding)
            .where(RiskFinding.id == risk_id, self.owned_by(user_id))
            .options(selectinload(RiskFinding.citations))
        )
        return result.scalar_one_or_none()
