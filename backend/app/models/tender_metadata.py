"""Extracted tender-level metadata, one row per analysis."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKeyConstraint, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    pass


class TenderMetadata(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "tender_metadata"
    __table_args__ = (
        ForeignKeyConstraint(
            ["analysis_id", "owner_user_id"],
            ["analyses.id", "analyses.owner_user_id"],
            name="fk_tender_metadata_analysis_owner",
            ondelete="CASCADE",
        ),
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    #: One metadata row per analysis.
    analysis_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), unique=True, nullable=False)

    buyer: Mapped[str | None] = mapped_column(String(255), default=None)
    reference: Mapped[str | None] = mapped_column(String(120), default=None)
    submission_deadline_text: Mapped[str | None] = mapped_column(String(120), default=None)
    contract_duration: Mapped[str | None] = mapped_column(String(120), default=None)
    estimated_value: Mapped[str | None] = mapped_column(String(120), default=None)
    currency: Mapped[str | None] = mapped_column(String(8), default=None)
    summary: Mapped[str | None] = mapped_column(Text, default=None)

    def __repr__(self) -> str:
        return f"<TenderMetadata analysis_id={self.analysis_id}>"
