"""A tender project — the container for uploaded documents and analyses."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.enums import TenderStatus
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.document import Document


class Tender(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tenders"
    __table_args__ = (
        # Supports the composite foreign key on documents — same ownership pattern as
        # company_profiles (docs/08 D27).
        UniqueConstraint("id", "owner_user_id", name="uq_tenders_id_owner_user_id"),
        CheckConstraint(f"status IN ({TenderStatus.sql_in_list()})", name="status"),
        Index("ix_tenders_owner_status", "owner_user_id", "status"),
        Index("ix_tenders_owner_deadline", "owner_user_id", "submission_deadline"),
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    buyer: Mapped[str | None] = mapped_column(String(255), default=None)
    reference: Mapped[str | None] = mapped_column(String(120), default=None)
    industry: Mapped[str | None] = mapped_column(String(120), default=None)
    #: Timezone-aware: submission deadlines are compared against `now()` for deadline scoring.
    submission_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=TenderStatus.ACTIVE.value
    )
    notes: Mapped[str | None] = mapped_column(Text, default=None)

    documents: Mapped[list[Document]] = relationship(
        back_populates="tender",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Tender id={self.id} status={self.status}>"
