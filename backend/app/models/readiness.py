"""The deterministic readiness assessment for an analysis (Phase 9).

Stores the calculated score, decision label, dimension breakdown, and hard blockers as JSONB,
plus a nullable human override that preserves the machine result (`docs/04` §2).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.domain.enums import DecisionLabel
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class ReadinessAssessment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "readiness_assessments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["analysis_id", "owner_user_id"],
            ["analyses.id", "analyses.owner_user_id"],
            name="fk_readiness_analysis_owner",
            ondelete="CASCADE",
        ),
        # One assessment per analysis.
        CheckConstraint("overall_score >= 0 AND overall_score <= 100", name="overall_score_range"),
        CheckConstraint(f"decision_label IN ({DecisionLabel.sql_in_list()})", name="label"),
        CheckConstraint(
            f"human_override_label IS NULL OR human_override_label IN "
            f"({DecisionLabel.sql_in_list()})",
            name="override_label",
        ),
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    analysis_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), unique=True, nullable=False)

    overall_score: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False)
    decision_label: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Full per-dimension breakdown, hard blockers, and assumptions — the explainable record.
    dimension_scores: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    hard_blockers: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    assumptions: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(16), nullable=False)

    #: Human override. Preserves the machine label/score above; a reason is required when set.
    human_override_label: Mapped[str | None] = mapped_column(String(32), default=None)
    human_override_reason: Mapped[str | None] = mapped_column(Text, default=None)

    def __repr__(self) -> str:
        return f"<ReadinessAssessment analysis_id={self.analysis_id} score={self.overall_score}>"
