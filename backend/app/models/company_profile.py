"""The company knowledge base root.

One profile per user, enforced by a unique constraint on `owner_user_id` — in the database, not
just in the service, so a concurrent double-POST cannot create two.

**Array columns.** Three fields use `text[]`: `licence_activities`, `service_categories`, and
`geographic_coverage`. Each is a genuine unordered list of short labels with no attributes of
its own, queried only for containment ("does this company cover Dubai?"), which a GIN index
serves directly. A child table would add a join and a migration for no gain, and JSONB would
add nesting that the data does not have. Everything with attributes — projects, evidence — is a
real table instead.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.enums import Emirate, RevenueRange
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.company_evidence import CompanyEvidence
    from app.models.company_project import CompanyProject

#: `MutableList` so an in-place `append` is tracked. Without it SQLAlchemy only notices a whole
#: reassignment, and a partial update that appended one activity would silently not persist.
StringArray = MutableList.as_mutable(ARRAY(Text))

MAX_DESCRIPTION_LENGTH = 4000

#: Sanity bounds only. "Not in the future" is enforced in the schema layer, because a check
#: constraint cannot call `now()` — it must be immutable.
MIN_YEAR_ESTABLISHED = 1800
MAX_YEAR_ESTABLISHED = 2200


class CompanyProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "company_profiles"
    __table_args__ = (
        # One primary profile per user, guaranteed by the database.
        UniqueConstraint("owner_user_id", name="uq_company_profiles_owner_user_id"),
        # Exists purely so children can carry a composite foreign key on
        # (company_profile_id, owner_user_id) — see CompanyEvidence.
        UniqueConstraint("id", "owner_user_id", name="uq_company_profiles_id_owner_user_id"),
        CheckConstraint(f"emirate IN ({Emirate.sql_in_list()})", name="emirate"),
        CheckConstraint(
            f"annual_revenue_range IS NULL "
            f"OR annual_revenue_range IN ({RevenueRange.sql_in_list()})",
            name="revenue_range",
        ),
        CheckConstraint("employee_count >= 0", name="employee_count"),
        CheckConstraint("years_of_experience >= 0", name="experience"),
        CheckConstraint(
            f"year_established BETWEEN {MIN_YEAR_ESTABLISHED} AND {MAX_YEAR_ESTABLISHED}",
            name="year_established",
        ),
        CheckConstraint(
            "preferred_contract_value_min IS NULL OR preferred_contract_value_min >= 0",
            name="contract_min_positive",
        ),
        CheckConstraint(
            "preferred_contract_value_max IS NULL OR preferred_contract_value_max >= 0",
            name="contract_max_positive",
        ),
        CheckConstraint(
            "preferred_contract_value_min IS NULL "
            "OR preferred_contract_value_max IS NULL "
            "OR preferred_contract_value_min <= preferred_contract_value_max",
            name="contract_range",
        ),
        CheckConstraint(
            "cardinality(service_categories) >= 1",
            name="service_categories_present",
        ),
        CheckConstraint(
            "cardinality(geographic_coverage) >= 1",
            name="geographic_coverage_present",
        ),
        CheckConstraint(
            "profile_completion_percentage BETWEEN 0 AND 100",
            name="completion_range",
        ),
        Index("ix_company_profiles_emirate", "emirate"),
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # --- Identity ---
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    trading_name: Mapped[str | None] = mapped_column(String(255), default=None)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    industry: Mapped[str] = mapped_column(String(120), nullable=False)

    # --- Location ---
    emirate: Mapped[str] = mapped_column(String(32), nullable=False)
    country: Mapped[str] = mapped_column(
        String(100), nullable=False, default="United Arab Emirates"
    )

    # --- Scale ---
    year_established: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    employee_count: Mapped[int] = mapped_column(Integer, nullable=False)
    years_of_experience: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    # --- Licence ---
    trade_licence_number: Mapped[str] = mapped_column(String(100), nullable=False)
    trade_licence_expiry: Mapped[date] = mapped_column(Date, nullable=False)
    licence_activities: Mapped[list[str]] = mapped_column(StringArray, nullable=False, default=list)

    # --- Contact ---
    website: Mapped[str | None] = mapped_column(String(255), default=None)
    contact_email: Mapped[str] = mapped_column(String(320), nullable=False)
    contact_phone: Mapped[str | None] = mapped_column(String(40), default=None)

    # --- Commercial preferences ---
    annual_revenue_range: Mapped[str | None] = mapped_column(String(40), default=None)
    #: Numeric, never float: contract values are money and are compared against tender
    #: thresholds, where binary rounding error is unacceptable.
    preferred_contract_value_min: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2), default=None
    )
    preferred_contract_value_max: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2), default=None
    )

    # --- Capability ---
    service_categories: Mapped[list[str]] = mapped_column(StringArray, nullable=False, default=list)
    geographic_coverage: Mapped[list[str]] = mapped_column(
        StringArray, nullable=False, default=list
    )

    # --- Derived, recalculated on every write (see app.domain.completion) ---
    #: Persisted so future list views can sort and filter without recomputing every row. Reads
    #: always serve a freshly calculated score, so a stale stored value is never returned.
    profile_completion_percentage: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0
    )
    completion_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1.0.0")

    evidence: Mapped[list[CompanyEvidence]] = relationship(
        back_populates="company_profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    projects: Mapped[list[CompanyProject]] = relationship(
        back_populates="company_profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<CompanyProfile id={self.id} owner_user_id={self.owner_user_id}>"
