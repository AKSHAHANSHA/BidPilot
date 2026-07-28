"""Request and response schemas for the marketplace layer."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.categories import is_valid_category
from app.domain.enums import ApplicationStatus, MarketProjectStatus


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


class CategoryRead(BaseModel):
    slug: str
    label: str
    icon: str


# ---------------------------------------------------------------------------
# Projects (public)
# ---------------------------------------------------------------------------


class ProjectSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    company_display_name: str
    category: str
    location: str | None
    budget_aed: Decimal | None
    submission_deadline: datetime | None
    cover_image_url: str | None
    status: str
    created_at: datetime


class ProjectDetail(ProjectSummary):
    description: str
    requirements_summary: str | None
    posted_by_user_id: uuid.UUID


class ProjectListResponse(BaseModel):
    items: list[ProjectSummary]
    total: int
    limit: int
    offset: int


class ProjectSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=12, ge=1, le=50)


# ---------------------------------------------------------------------------
# Projects (company create)
# ---------------------------------------------------------------------------


class ProjectCreate(BaseModel):
    title: Annotated[str, Field(min_length=3, max_length=255)]
    description: Annotated[str, Field(min_length=20, max_length=8000)]
    category: Annotated[str, Field(min_length=2, max_length=80)]
    location: str | None = Field(default=None, max_length=120)
    budget_aed: Decimal | None = Field(default=None, ge=0)
    submission_deadline: datetime | None = None
    cover_image_url: str | None = Field(default=None, max_length=1024)
    requirements_summary: str | None = Field(default=None, max_length=4000)
    is_public: bool = True

    @field_validator("category")
    @classmethod
    def _category_is_known(cls, value: str) -> str:
        if not is_valid_category(value):
            raise ValueError("Unknown category")
        return value


class ProjectUpdate(BaseModel):
    status: MarketProjectStatus | None = None
    is_public: bool | None = None


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------


class ApplicationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    vendor_user_id: uuid.UUID
    status: str
    ai_score: int | None
    ai_summary: str | None
    submitted_at: datetime


class ApplicationDetail(ApplicationSummary):
    ai_assessment: dict[str, Any] | None
    document_original_name: str | None
    reviewed_at: datetime | None
    review_note: str | None


class ApplicationCreate(BaseModel):
    project_id: uuid.UUID
    cover_letter: str | None = Field(default=None, max_length=4000)


class ApplicationReview(BaseModel):
    status: ApplicationStatus
    note: str | None = Field(default=None, max_length=2000)


# ---------------------------------------------------------------------------
# Vendor dashboard
# ---------------------------------------------------------------------------


class VendorDashboardSummary(BaseModel):
    total_applications: int
    submitted: int
    screened: int
    shortlisted: int
    rejected: int
    average_ai_score: float | None
    applications: list[ApplicationSummary]


class CompanyDashboardSummary(BaseModel):
    total_projects: int
    open_projects: int
    total_applicants: int
    average_applicant_score: float | None
    recent_applications: list[ApplicationSummary]


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    title: str
    body: str | None
    payload: dict[str, Any] | None
    read_at: datetime | None
    created_at: datetime


class NotificationCounts(BaseModel):
    unread: int
    total: int
