"""Company project schemas.

The status/end-date relationship is enforced in three places on purpose: here for a clear 422,
in the service for partial updates that can only be judged against persisted state, and in a
database check constraint so no path can write a contradictory row.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.enums import ProjectStatus

MAX_DESCRIPTION_LENGTH = 4000
MAX_SERVICES = 30

Money = Annotated[Decimal, Field(ge=0, le=Decimal("99999999999.99"), decimal_places=2)]
Service = Annotated[str, Field(min_length=1, max_length=120)]
ServiceList = Annotated[list[Service], Field(min_length=1, max_length=MAX_SERVICES)]


def _clean_services(values: list[str]) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for value in values:
        item = value.strip()
        if item and item.casefold() not in seen:
            seen.add(item.casefold())
            cleaned.append(item)
    return cleaned


class ProjectBase(BaseModel):
    client_name: Annotated[str, Field(min_length=1, max_length=255)]
    project_title: Annotated[str, Field(min_length=1, max_length=255)]
    industry: Annotated[str, Field(min_length=1, max_length=120)]
    description: Annotated[str, Field(min_length=1, max_length=MAX_DESCRIPTION_LENGTH)]
    contract_value: Money | None = None
    currency: Annotated[str, Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")] = "AED"
    start_date: date
    end_date: date | None = None
    status: ProjectStatus
    location: Annotated[str, Field(min_length=1, max_length=160)]
    services_delivered: ServiceList
    outcome: Annotated[str | None, Field(max_length=MAX_DESCRIPTION_LENGTH)] = None
    client_reference_available: bool = False
    is_confidential: bool = False

    @field_validator("services_delivered")
    @classmethod
    def _normalize_services(cls, value: list[str]) -> list[str]:
        cleaned = _clean_services(value)
        if not cleaned:
            raise ValueError("At least one delivered service is required")
        return cleaned

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, value: str) -> str:
        return value.upper()

    @field_validator("start_date")
    @classmethod
    def _start_not_in_the_future(cls, value: date) -> date:
        # A project that has not begun is not experience.
        if value > datetime.now(tz=UTC).date():
            raise ValueError("Project start date cannot be in the future")
        return value

    @model_validator(mode="after")
    def _validate_status_and_dates(self) -> ProjectBase:
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("Project end date cannot be earlier than the start date")

        if self.status is ProjectStatus.CURRENT and self.end_date is not None:
            raise ValueError("A current project cannot have an end date")

        if self.status is ProjectStatus.COMPLETED and self.end_date is None:
            raise ValueError("A completed project requires an end date")

        return self


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_name: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    project_title: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    industry: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    description: Annotated[str, Field(min_length=1, max_length=MAX_DESCRIPTION_LENGTH)] | None = (
        None
    )
    contract_value: Money | None = None
    currency: Annotated[str, Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")] | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: ProjectStatus | None = None
    location: Annotated[str, Field(min_length=1, max_length=160)] | None = None
    services_delivered: ServiceList | None = None
    outcome: Annotated[str | None, Field(max_length=MAX_DESCRIPTION_LENGTH)] = None
    client_reference_available: bool | None = None
    is_confidential: bool | None = None

    @field_validator("services_delivered")
    @classmethod
    def _normalize_services(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = _clean_services(value)
        if not cleaned:
            raise ValueError("At least one delivered service is required")
        return cleaned

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None

    @model_validator(mode="after")
    def _validate_supplied_dates(self) -> ProjectUpdate:
        # The status/end-date rule needs the persisted row when only one side is supplied, so the
        # service completes the check. Here we can only judge what arrived together.
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.end_date < self.start_date
        ):
            raise ValueError("Project end date cannot be earlier than the start date")
        return self


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_profile_id: str
    client_name: str
    project_title: str
    industry: str
    description: str
    contract_value: Decimal | None
    currency: str
    start_date: date
    end_date: date | None
    status: str
    location: str
    services_delivered: list[str]
    outcome: str | None
    client_reference_available: bool
    is_confidential: bool
    duration_months: int | None = Field(
        default=None,
        description="Whole months between start and end. Null while the project is current.",
    )
    created_at: datetime
    updated_at: datetime

    @field_validator("id", "company_profile_id", mode="before")
    @classmethod
    def _stringify(cls, value: object) -> str:
        return str(value)
