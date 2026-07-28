"""A vendor's application to a marketplace project.

Optionally carries an uploaded document (portfolio, credentials, quote) and, once the AI
screening actor runs, an `ai_score` in 0..100 plus an `ai_assessment` payload with a short
plain-English summary. Scoring is deterministic Python over LLM-extracted structured claims
— never an LLM-guessed score (same rule as the bid-readiness pipeline).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.enums import ApplicationStatus
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.market_project import MarketProject


class Application(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "applications"
    __table_args__ = (
        # One application per vendor per project — a resubmit updates the row rather than
        # creating a duplicate.
        UniqueConstraint("project_id", "vendor_user_id", name="uq_applications_project_vendor"),
        CheckConstraint(
            f"status IN ({ApplicationStatus.sql_in_list()})", name="application_status"
        ),
        CheckConstraint(
            "ai_score IS NULL OR (ai_score >= 0 AND ai_score <= 100)",
            name="ai_score_range",
        ),
        Index("ix_applications_vendor_status", "vendor_user_id", "status"),
        Index("ix_applications_project_status", "project_id", "status"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("market_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    vendor_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    #: Server-generated storage key for the vendor's uploaded document, or NULL if the vendor
    #: applied without a file. Same opaque-key contract as tender uploads: never a client name.
    document_storage_key: Mapped[str | None] = mapped_column(String(512), default=None)
    document_original_name: Mapped[str | None] = mapped_column(String(255), default=None)

    ai_score: Mapped[int | None] = mapped_column(Integer, default=None)
    ai_summary: Mapped[str | None] = mapped_column(String(2000), default=None)
    ai_assessment: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ApplicationStatus.SUBMITTED.value
    )
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    review_note: Mapped[str | None] = mapped_column(String(2000), default=None)

    project: Mapped[MarketProject] = relationship(back_populates="applications")

    def __repr__(self) -> str:
        return f"<Application id={self.id} project={self.project_id} status={self.status}>"
