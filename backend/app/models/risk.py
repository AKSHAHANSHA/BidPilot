"""Risk findings and their citations (Phase 8).

Risks are cited, advisory, and human-reviewable. The model reports clauses; it does not give
legal conclusions (`docs/03` §10). Only findings with a verified citation are canonical, the
same rule as requirements.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.enums import (
    CitationMatchMethod,
    ComplianceStatus,
    RiskSeverity,
    RiskType,
)
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    pass


class RiskFinding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "risk_findings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["analysis_id", "owner_user_id"],
            ["analyses.id", "analyses.owner_user_id"],
            name="fk_risk_findings_analysis_owner",
            ondelete="CASCADE",
        ),
        UniqueConstraint("id", "owner_user_id", name="uq_risk_findings_id_owner_user_id"),
        CheckConstraint(f"risk_type IN ({RiskType.sql_in_list()})", name="risk_type"),
        CheckConstraint(f"severity IN ({RiskSeverity.sql_in_list()})", name="severity"),
        CheckConstraint(
            f"reviewed_status IN ({ComplianceStatus.sql_in_list()})", name="reviewed_status"
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        Index("ix_risk_findings_analysis_owner", "analysis_id", "owner_user_id"),
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    analysis_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    risk_type: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    why_it_matters: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_action: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    citation_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    reviewed_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=ComplianceStatus.UNREVIEWED.value
    )
    review_reason: Mapped[str | None] = mapped_column(Text, default=None)

    citations: Mapped[list[RiskCitation]] = relationship(
        back_populates="risk",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<RiskFinding id={self.id} type={self.risk_type} severity={self.severity}>"


class RiskCitation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "risk_citations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["risk_id", "owner_user_id"],
            ["risk_findings.id", "risk_findings.owner_user_id"],
            name="fk_risk_citations_risk_owner",
            ondelete="CASCADE",
        ),
        CheckConstraint("page_number >= 1", name="page_number_positive"),
        CheckConstraint(
            f"match_method IN ({CitationMatchMethod.sql_in_list()})", name="match_method"
        ),
        CheckConstraint(
            "match_score IS NULL OR (match_score >= 0 AND match_score <= 1)",
            name="match_score_range",
        ),
        Index("ix_risk_citations_risk_owner", "risk_id", "owner_user_id"),
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    risk_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_quote: Mapped[str] = mapped_column(Text, nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    match_method: Mapped[str] = mapped_column(
        String(16), nullable=False, default=CitationMatchMethod.UNVERIFIED.value
    )
    match_score: Mapped[float | None] = mapped_column(Float, default=None)

    risk: Mapped[RiskFinding] = relationship(back_populates="citations")

    def __repr__(self) -> str:
        return f"<RiskCitation risk={self.risk_id} page={self.page_number}>"
