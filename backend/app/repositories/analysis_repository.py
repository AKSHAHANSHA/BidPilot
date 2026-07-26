"""Analysis persistence, ownership-enforced."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.domain.enums import AnalysisStatus
from app.models.analysis import Analysis
from app.repositories.base import OwnedRepository


class AnalysisRepository(OwnedRepository[Analysis]):
    model = Analysis
    owner_field = "owner_user_id"

    async def list_for_tender(self, tender_id: uuid.UUID, user_id: uuid.UUID) -> list[Analysis]:
        result = await self.session.execute(
            select(Analysis)
            .where(Analysis.tender_id == tender_id, self.owned_by(user_id))
            .order_by(Analysis.version.desc())
        )
        return list(result.scalars().all())

    async def latest_for_tender(self, tender_id: uuid.UUID, user_id: uuid.UUID) -> Analysis | None:
        result = await self.session.execute(
            select(Analysis)
            .where(Analysis.tender_id == tender_id, self.owned_by(user_id))
            .order_by(Analysis.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def next_version(self, tender_id: uuid.UUID, user_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.coalesce(func.max(Analysis.version), 0)).where(
                Analysis.tender_id == tender_id, self.owned_by(user_id)
            )
        )
        return int(result.scalar_one()) + 1

    async def active_for_tender(self, tender_id: uuid.UUID, user_id: uuid.UUID) -> Analysis | None:
        """A queued or processing run, if one exists — used to prevent duplicate concurrent runs."""
        result = await self.session.execute(
            select(Analysis).where(
                Analysis.tender_id == tender_id,
                self.owned_by(user_id),
                Analysis.status.in_([AnalysisStatus.QUEUED.value, AnalysisStatus.PROCESSING.value]),
            )
        )
        return result.scalars().first()
