"""How a requirement matched against company evidence (Phase 8)."""

from __future__ import annotations

import uuid

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.domain.enums import MatchStatus
from app.models.base import UUIDPrimaryKeyMixin

StringArray = MutableList.as_mutable(ARRAY(Text))


class RequirementEvidenceMatch(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "requirement_evidence_matches"
    __table_args__ = (
        ForeignKeyConstraint(
            ["requirement_id", "owner_user_id"],
            ["requirements.id", "requirements.owner_user_id"],
            name="fk_evidence_matches_requirement_owner",
            ondelete="CASCADE",
        ),
        CheckConstraint(f"status IN ({MatchStatus.sql_in_list()})", name="status"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        Index("ix_evidence_matches_requirement", "requirement_id", "owner_user_id"),
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    requirement_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    status: Mapped[str] = mapped_column(String(24), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    #: IDs of the company evidence items that satisfied the requirement (may be empty).
    matched_evidence_ids: Mapped[list[str]] = mapped_column(
        StringArray, nullable=False, default=list
    )
    missing_evidence: Mapped[list[str]] = mapped_column(StringArray, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    #: True for a deterministic rule; False when a semantic assist produced the verdict.
    is_deterministic: Mapped[bool] = mapped_column(nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<RequirementEvidenceMatch req={self.requirement_id} status={self.status}>"
