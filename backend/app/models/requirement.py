"""Extracted requirements and their citations.

A requirement is canonical evidence only once its citation is verified (Phase 7). Phase 6
persists requirements with `citation_verified=False`; Phase 7 flips that after checking the
quote against the cited page. `machine_status`/`reviewed_status` carry the compliance verdict
from Phase 8 and human review.
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
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.enums import (
    CitationMatchMethod,
    ComplianceStatus,
    RequirementCategory,
    RequirementObligation,
)
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    pass

StringArray = MutableList.as_mutable(ARRAY(Text))


class Requirement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "requirements"
    __table_args__ = (
        ForeignKeyConstraint(
            ["analysis_id", "owner_user_id"],
            ["analyses.id", "analyses.owner_user_id"],
            name="fk_requirements_analysis_owner",
            ondelete="CASCADE",
        ),
        UniqueConstraint("id", "owner_user_id", name="uq_requirements_id_owner_user_id"),
        CheckConstraint(f"category IN ({RequirementCategory.sql_in_list()})", name="category"),
        CheckConstraint(
            f"obligation IN ({RequirementObligation.sql_in_list()})", name="obligation"
        ),
        CheckConstraint(
            f"machine_status IN ({ComplianceStatus.sql_in_list()})", name="machine_status"
        ),
        CheckConstraint(
            f"reviewed_status IN ({ComplianceStatus.sql_in_list()})", name="reviewed_status"
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        Index("ix_requirements_analysis_owner", "analysis_id", "owner_user_id"),
        Index("ix_requirements_analysis_category", "analysis_id", "category"),
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    analysis_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    category: Mapped[str] = mapped_column(String(40), nullable=False)
    obligation: Mapped[str] = mapped_column(String(16), nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    expected_evidence: Mapped[list[str]] = mapped_column(StringArray, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    #: True once at least one citation is verified (Phase 7). Only verified requirements are
    #: treated as canonical material findings (`docs/03` §6).
    citation_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    machine_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=ComplianceStatus.UNREVIEWED.value
    )
    reviewed_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=ComplianceStatus.UNREVIEWED.value
    )
    review_reason: Mapped[str | None] = mapped_column(Text, default=None)

    citations: Mapped[list[RequirementCitation]] = relationship(
        back_populates="requirement",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Requirement id={self.id} category={self.category}>"


class RequirementCitation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "requirement_citations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["requirement_id", "owner_user_id"],
            ["requirements.id", "requirements.owner_user_id"],
            name="fk_requirement_citations_requirement_owner",
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
        Index("ix_requirement_citations_requirement_owner", "requirement_id", "owner_user_id"),
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    requirement_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_quote: Mapped[str] = mapped_column(Text, nullable=False)
    #: Verification fields — set by Phase 7. Until then verified=False, method=unverified.
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    match_method: Mapped[str] = mapped_column(
        String(16), nullable=False, default=CitationMatchMethod.UNVERIFIED.value
    )
    match_score: Mapped[float | None] = mapped_column(Float, default=None)

    requirement: Mapped[Requirement] = relationship(back_populates="citations")

    def __repr__(self) -> str:
        return f"<RequirementCitation req={self.requirement_id} page={self.page_number}>"
