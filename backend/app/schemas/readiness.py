"""Readiness assessment read and override schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import DecisionLabel


class DimensionRead(BaseModel):
    key: str
    label: str
    raw_score: float
    weight: int
    weighted_score: float
    explanation: str


class HardBlockerRead(BaseModel):
    code: str
    message: str


class HumanOverrideRead(BaseModel):
    label: DecisionLabel
    reason: str


class ReadinessRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    analysis_id: str
    overall_score: Decimal
    decision_label: DecisionLabel
    dimensions: list[DimensionRead]
    hard_blockers: list[HardBlockerRead]
    assumptions: list[str]
    calculation_version: str
    human_override: HumanOverrideRead | None
    created_at: datetime

    @classmethod
    def from_model(cls, assessment: object) -> ReadinessRead:
        a = assessment
        override = None
        if a.human_override_label is not None:  # type: ignore[attr-defined]
            override = HumanOverrideRead(
                label=DecisionLabel(a.human_override_label),  # type: ignore[attr-defined]
                reason=a.human_override_reason or "",  # type: ignore[attr-defined]
            )
        return cls(
            analysis_id=str(a.analysis_id),  # type: ignore[attr-defined]
            overall_score=a.overall_score,  # type: ignore[attr-defined]
            decision_label=DecisionLabel(a.decision_label),  # type: ignore[attr-defined]
            dimensions=[DimensionRead(**d) for d in a.dimension_scores],  # type: ignore[attr-defined]
            hard_blockers=[HardBlockerRead(**b) for b in a.hard_blockers],  # type: ignore[attr-defined]
            assumptions=list(a.assumptions),  # type: ignore[attr-defined]
            calculation_version=a.calculation_version,  # type: ignore[attr-defined]
            human_override=override,
            created_at=a.created_at,  # type: ignore[attr-defined]
        )


class ReadinessOverrideRequest(BaseModel):
    """A human override of the decision label. The machine score/label is preserved."""

    decision_label: DecisionLabel
    reason: Annotated[str, Field(min_length=3, max_length=2000)]

    @field_validator("reason")
    @classmethod
    def _reason_substantive(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 3:
            raise ValueError("An override reason is required.")
        return stripped
