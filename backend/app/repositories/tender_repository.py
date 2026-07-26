"""Tender and document persistence, ownership-enforced."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.sql.functions import concat

from app.domain.enums import TenderStatus
from app.models.document import Document
from app.models.tender import Tender
from app.repositories.base import OwnedRepository


@dataclass(frozen=True, slots=True)
class TenderFilters:
    status: TenderStatus | None = None
    search: str | None = None
    deadline_before: datetime | None = None
    deadline_after: datetime | None = None


class TenderRepository(OwnedRepository[Tender]):
    model = Tender
    owner_field = "owner_user_id"

    @staticmethod
    def _search_predicate(term: str) -> ColumnElement[bool]:
        escaped = term.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = concat("%", escaped, "%")
        return or_(
            Tender.title.ilike(pattern, escape="\\"),
            Tender.buyer.ilike(pattern, escape="\\"),
            Tender.reference.ilike(pattern, escape="\\"),
        )

    async def list_filtered(
        self,
        user_id: uuid.UUID,
        filters: TenderFilters,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[Tender], int]:
        base = select(Tender).where(self.owned_by(user_id))
        if filters.status is not None:
            base = base.where(Tender.status == filters.status.value)
        if filters.search:
            base = base.where(self._search_predicate(filters.search))
        if filters.deadline_before is not None:
            base = base.where(Tender.submission_deadline <= filters.deadline_before)
        if filters.deadline_after is not None:
            base = base.where(Tender.submission_deadline >= filters.deadline_after)

        total = int(
            (
                await self.session.execute(select(func.count()).select_from(base.subquery()))
            ).scalar_one()
        )
        rows = await self.session.execute(
            base.order_by(Tender.created_at.desc(), Tender.id.desc()).limit(limit).offset(offset)
        )
        return list(rows.scalars().all()), total


class DocumentRepository(OwnedRepository[Document]):
    model = Document
    owner_field = "owner_user_id"

    async def list_for_tender(self, tender_id: uuid.UUID, user_id: uuid.UUID) -> list[Document]:
        result = await self.session.execute(
            select(Document)
            .where(Document.tender_id == tender_id, self.owned_by(user_id))
            .order_by(Document.created_at.desc())
        )
        return list(result.scalars().all())

    async def find_duplicate(
        self, tender_id: uuid.UUID, user_id: uuid.UUID, sha256: str
    ) -> Document | None:
        result = await self.session.execute(
            select(Document).where(
                Document.tender_id == tender_id,
                self.owned_by(user_id),
                Document.sha256 == sha256,
            )
        )
        return result.scalar_one_or_none()

    async def storage_keys_for_tender(self, tender_id: uuid.UUID, user_id: uuid.UUID) -> list[str]:
        """Keys of every file belonging to a tender, for cleanup after a cascade delete."""
        result = await self.session.execute(
            select(Document.storage_key).where(
                Document.tender_id == tender_id, self.owned_by(user_id)
            )
        )
        return list(result.scalars().all())
