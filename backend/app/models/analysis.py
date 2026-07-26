"""An analysis run over a tender's document — the job whose state the pipeline advances.

PostgreSQL is the authoritative record of job status, not Redis (`docs/02` §4). Every stage
transition is a committed write here, so a crashed or restarted worker never loses the fact
that a job was in progress, and the API can report status without consulting the broker.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.enums import AnalysisStage, AnalysisStatus
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.tender import Tender


class Analysis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "analyses"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tender_id", "owner_user_id"],
            ["tenders.id", "tenders.owner_user_id"],
            name="fk_analyses_tender_owner",
            ondelete="CASCADE",
        ),
        # Analysis versions per tender are monotonic; rerunning a completed analysis creates
        # the next version rather than mutating history.
        UniqueConstraint("tender_id", "version", name="uq_analyses_tender_version"),
        # Supports child findings' composite ownership foreign key from Phase 6 onward.
        UniqueConstraint("id", "owner_user_id", name="uq_analyses_id_owner_user_id"),
        CheckConstraint(f"status IN ({AnalysisStatus.sql_in_list()})", name="status"),
        CheckConstraint(f"current_stage IN ({AnalysisStage.sql_in_list()})", name="stage"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("attempt_count >= 0", name="attempt_count_positive"),
        CheckConstraint("input_tokens >= 0 AND output_tokens >= 0", name="tokens_positive"),
        Index("ix_analyses_tender_owner", "tender_id", "owner_user_id"),
        Index("ix_analyses_owner_status", "owner_user_id", "status"),
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    tender_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    #: The document this run analyses. Nullable so a run can be recorded even if the document
    #: is later deleted; the pipeline resolves it at validation time.
    document_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), default=None)

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=AnalysisStatus.QUEUED.value
    )
    current_stage: Mapped[str] = mapped_column(
        String(32), nullable=False, default=AnalysisStage.QUEUED.value
    )
    #: Human-facing, no fabricated percentages (`docs/05` processing room, CLAUDE.md).
    stage_message: Mapped[str | None] = mapped_column(String(255), default=None)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Safe failure code; the developer-facing detail is logged, never stored or returned.
    error_code: Mapped[str | None] = mapped_column(String(32), default=None)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    # --- Provenance and cost (populated from Phase 6) ---
    provider: Mapped[str | None] = mapped_column(String(32), default=None)
    model: Mapped[str | None] = mapped_column(String(80), default=None)
    prompt_version: Mapped[str | None] = mapped_column(String(16), default=None)
    scoring_version: Mapped[str | None] = mapped_column(String(16), default=None)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, default=Decimal("0")
    )

    #: Free-text summary of what the run produced; structured findings arrive in later phases.
    summary: Mapped[str | None] = mapped_column(Text, default=None)

    tender: Mapped[Tender] = relationship(back_populates="analyses")

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            AnalysisStatus.COMPLETED.value,
            AnalysisStatus.FAILED.value,
            AnalysisStatus.CANCELLED.value,
        }

    @property
    def can_retry(self) -> bool:
        return self.status == AnalysisStatus.FAILED.value

    def __repr__(self) -> str:
        return f"<Analysis id={self.id} v{self.version} status={self.status}>"
