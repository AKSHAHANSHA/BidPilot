"""A marketplace tender posted by a company for vendors to browse and apply to.

Deliberately independent from `Tender` (which the existing bid-readiness pipeline owns).
The two entities describe opposite lifecycle ends: `Tender` is a contractor deciding whether
to bid on a downloaded PDF; `MarketProject` is a public listing a company publishes for
vendors to see. Keeping them separate avoids reshaping the analysis schema and lets each
evolve on its own.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.enums import MarketProjectStatus
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.application import Application


class MarketProject(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "market_projects"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({MarketProjectStatus.sql_in_list()})", name="market_project_status"
        ),
        CheckConstraint(
            "budget_aed IS NULL OR budget_aed >= 0", name="market_project_budget_positive"
        ),
        Index("ix_market_projects_status_deadline", "status", "submission_deadline"),
        Index("ix_market_projects_category", "category"),
        Index("ix_market_projects_posted_by", "posted_by_user_id"),
    )

    posted_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    #: Denormalised copy of the company's public name so the listing can render without
    #: joining company_profiles — profiles are optional on signup and can be missing.
    company_display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    location: Mapped[str | None] = mapped_column(String(120), default=None)
    #: Numeric, never float, for the same reason CompanyProfile uses Numeric on contract values.
    budget_aed: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)
    submission_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    cover_image_url: Mapped[str | None] = mapped_column(String(1024), default=None)
    requirements_summary: Mapped[str | None] = mapped_column(Text, default=None)
    #: Whether this project is visible on the public landing/browse pages.
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=MarketProjectStatus.OPEN.value
    )

    applications: Mapped[list[Application]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<MarketProject id={self.id} status={self.status} category={self.category}>"
