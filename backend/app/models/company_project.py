"""A delivered or in-progress project — the company's experience record.

A separate table rather than an evidence subtype. Phase 8 has to answer questions like "three
similar projects above AED 2M in Dubai within the last five years", which needs typed, indexed
columns for value, dates, location, and services. Folding those into `company_evidence` would
mean either JSONB or eleven mostly-NULL columns that are meaningless for every other category.

`previous_project` remains a valid *evidence* category: a completion certificate is a document
*about* a project, while this row is the structured claim. Linking the two with a nullable
foreign key later is additive, so it is not needed now.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.enums import ProjectStatus
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.company_profile import CompanyProfile

StringArray = MutableList.as_mutable(ARRAY(Text))

MAX_DESCRIPTION_LENGTH = 4000


class CompanyProject(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "company_projects"
    __table_args__ = (
        # Same composite-key guarantee as evidence: a project cannot be attached to a profile
        # the caller does not own.
        ForeignKeyConstraint(
            ["company_profile_id", "owner_user_id"],
            ["company_profiles.id", "company_profiles.owner_user_id"],
            name="fk_company_projects_profile_owner",
            ondelete="CASCADE",
        ),
        CheckConstraint(f"status IN ({ProjectStatus.sql_in_list()})", name="status"),
        CheckConstraint("end_date IS NULL OR start_date <= end_date", name="date_order"),
        # State integrity: an in-progress project has no end date, and a completed one must have
        # one. Without this a project could claim to be current while also having ended.
        CheckConstraint(
            "(status = 'current' AND end_date IS NULL) "
            "OR (status = 'completed' AND end_date IS NOT NULL)",
            name="status_end_date",
        ),
        CheckConstraint(
            "contract_value IS NULL OR contract_value >= 0",
            name="contract_value",
        ),
        CheckConstraint(
            "cardinality(services_delivered) >= 1",
            name="services_present",
        ),
        Index("ix_company_projects_profile_owner", "company_profile_id", "owner_user_id"),
        Index("ix_company_projects_owner_status", "owner_user_id", "status"),
        # Recency filtering ("projects in the last five years") sorts on this.
        Index("ix_company_projects_start_date", "start_date"),
        Index("ix_company_projects_services", "services_delivered", postgresql_using="gin"),
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    company_profile_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    client_name: Mapped[str] = mapped_column(String(255), nullable=False)
    project_title: Mapped[str] = mapped_column(String(255), nullable=False)
    industry: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    contract_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)
    #: A contract value without a currency cannot be compared against a tender threshold, so the
    #: unit is stored explicitly rather than assumed.
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="AED")

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, default=None)
    status: Mapped[str] = mapped_column(String(16), nullable=False)

    location: Mapped[str] = mapped_column(String(160), nullable=False)
    services_delivered: Mapped[list[str]] = mapped_column(StringArray, nullable=False, default=list)
    outcome: Mapped[str | None] = mapped_column(Text, default=None)

    client_reference_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Set when the client forbids naming them. Later phases must not quote a confidential
    #: project's client in a report.
    is_confidential: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    company_profile: Mapped[CompanyProfile] = relationship(back_populates="projects")

    def __repr__(self) -> str:
        return f"<CompanyProject id={self.id} status={self.status}>"
