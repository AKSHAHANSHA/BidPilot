"""Company profile schemas.

Validation that depends on the current date (a year of establishment in the future) lives here
rather than in a database check constraint, because a check constraint must be immutable and
cannot call `now()`. The database still enforces the immutable half — sane bounds, non-negative
counts, min <= max — so both layers do the part they are actually good at.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)

from app.domain.completion import CompletionResult
from app.domain.enums import Emirate, RevenueRange

MAX_DESCRIPTION_LENGTH = 4000
MAX_ARRAY_ITEMS = 40
MAX_ARRAY_ITEM_LENGTH = 120

#: Money is never a float. `Decimal` all the way from the request body to the numeric column.
Money = Annotated[Decimal, Field(ge=0, le=Decimal("99999999999.99"), decimal_places=2)]
ShortText = Annotated[str, Field(min_length=1, max_length=120)]
LongText = Annotated[str, Field(min_length=1, max_length=MAX_DESCRIPTION_LENGTH)]
StringList = Annotated[list[ShortText], Field(max_length=MAX_ARRAY_ITEMS)]


def _clean_items(values: list[str]) -> list[str]:
    """Trim, drop blanks, and de-duplicate case-insensitively while keeping order.

    List fields are matched against tender requirements later, so "Cleaning" and "cleaning "
    must not survive as two distinct capabilities.
    """
    seen: set[str] = set()
    cleaned: list[str] = []
    for value in values:
        item = value.strip()
        if not item:
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(item)
    return cleaned


class CompanyProfileBase(BaseModel):
    legal_name: Annotated[str, Field(min_length=2, max_length=255)]
    trading_name: Annotated[str | None, Field(max_length=255)] = None
    description: LongText
    industry: ShortText
    emirate: Emirate
    country: Annotated[str, Field(min_length=2, max_length=100)] = "United Arab Emirates"
    year_established: Annotated[int, Field(ge=1800, le=2200)]
    employee_count: Annotated[int, Field(ge=0, le=1_000_000)]
    years_of_experience: Annotated[int, Field(ge=0, le=200)]
    trade_licence_number: Annotated[str, Field(min_length=1, max_length=100)]
    trade_licence_expiry: date
    licence_activities: StringList
    website: HttpUrl | None = None
    contact_email: EmailStr
    contact_phone: Annotated[str | None, Field(max_length=40)] = None
    annual_revenue_range: RevenueRange | None = None
    preferred_contract_value_min: Money | None = None
    preferred_contract_value_max: Money | None = None
    service_categories: Annotated[StringList, Field(min_length=1)]
    geographic_coverage: Annotated[StringList, Field(min_length=1)]

    @field_validator("licence_activities", "service_categories", "geographic_coverage")
    @classmethod
    def _normalize_lists(cls, value: list[str]) -> list[str]:
        return _clean_items(value)

    @field_validator("legal_name", "trading_name", "industry", "trade_licence_number")
    @classmethod
    def _strip_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("year_established")
    @classmethod
    def _not_in_the_future(cls, value: int) -> int:
        current_year = datetime.now(tz=UTC).year
        if value > current_year:
            raise ValueError(f"Year established cannot be later than {current_year}")
        return value

    @model_validator(mode="after")
    def _validate_commercials(self) -> CompanyProfileBase:
        minimum = self.preferred_contract_value_min
        maximum = self.preferred_contract_value_max
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError(
                "Minimum preferred contract value cannot exceed the maximum preferred value"
            )
        if not self.service_categories:
            raise ValueError("At least one service category is required")
        if not self.geographic_coverage:
            raise ValueError("At least one geographic coverage entry is required")
        return self

    @model_validator(mode="after")
    def _experience_fits_company_age(self) -> CompanyProfileBase:
        # A company founded in 2020 cannot have 30 years of operating experience. Caught here
        # because it is a relationship between two fields, not a bound on either one.
        age = datetime.now(tz=UTC).year - self.year_established
        if self.years_of_experience > age + 1:
            raise ValueError(
                f"Years of experience ({self.years_of_experience}) exceeds the company's age "
                f"since {self.year_established}"
            )
        return self


class CompanyProfileCreate(CompanyProfileBase):
    """Full profile. Every required field must be present at creation."""


class CompanyProfileUpdate(BaseModel):
    """Partial update. Every field optional; omitted fields are left untouched.

    `PATCH` semantics mean "unset" and "absent" must be distinguishable, which is why nullable
    optional fields are typed `T | None` and the service applies only keys present in
    `model_fields_set`.
    """

    model_config = ConfigDict(extra="forbid")

    legal_name: Annotated[str, Field(min_length=2, max_length=255)] | None = None
    trading_name: Annotated[str | None, Field(max_length=255)] = None
    description: LongText | None = None
    industry: ShortText | None = None
    emirate: Emirate | None = None
    country: Annotated[str, Field(min_length=2, max_length=100)] | None = None
    year_established: Annotated[int, Field(ge=1800, le=2200)] | None = None
    employee_count: Annotated[int, Field(ge=0, le=1_000_000)] | None = None
    years_of_experience: Annotated[int, Field(ge=0, le=200)] | None = None
    trade_licence_number: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    trade_licence_expiry: date | None = None
    licence_activities: StringList | None = None
    website: HttpUrl | None = None
    contact_email: EmailStr | None = None
    contact_phone: Annotated[str | None, Field(max_length=40)] = None
    annual_revenue_range: RevenueRange | None = None
    preferred_contract_value_min: Money | None = None
    preferred_contract_value_max: Money | None = None
    service_categories: Annotated[StringList, Field(min_length=1)] | None = None
    geographic_coverage: Annotated[StringList, Field(min_length=1)] | None = None

    @field_validator("licence_activities", "service_categories", "geographic_coverage")
    @classmethod
    def _normalize_lists(cls, value: list[str] | None) -> list[str] | None:
        return _clean_items(value) if value is not None else None

    @field_validator("year_established")
    @classmethod
    def _not_in_the_future(cls, value: int | None) -> int | None:
        if value is None:
            return None
        current_year = datetime.now(tz=UTC).year
        if value > current_year:
            raise ValueError(f"Year established cannot be later than {current_year}")
        return value

    @model_validator(mode="after")
    def _validate_partial_range(self) -> CompanyProfileUpdate:
        # Only checkable when both bounds arrive together; a one-sided update is validated
        # against the persisted value in the service, which can see the other half.
        minimum = self.preferred_contract_value_min
        maximum = self.preferred_contract_value_max
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError(
                "Minimum preferred contract value cannot exceed the maximum preferred value"
            )
        return self


class CompletionComponentRead(BaseModel):
    key: str
    label: str
    group: str
    weight: int
    earned: bool
    hint: str


class CompletionRead(BaseModel):
    """The full completion breakdown, so the UI can explain the score instead of just showing it."""

    score: Annotated[int, Field(ge=0, le=100)]
    version: str
    components: list[CompletionComponentRead]
    missing: list[CompletionComponentRead]

    @classmethod
    def from_result(cls, result: CompletionResult) -> CompletionRead:
        return cls(
            score=result.score,
            version=result.version,
            components=[
                CompletionComponentRead(
                    key=component.key,
                    label=component.label,
                    group=component.group,
                    weight=component.weight,
                    earned=component.earned,
                    hint=component.hint,
                )
                for component in result.components
            ],
            missing=[
                CompletionComponentRead(
                    key=component.key,
                    label=component.label,
                    group=component.group,
                    weight=component.weight,
                    earned=component.earned,
                    hint=component.hint,
                )
                for component in result.missing
            ],
        )


class CompanyProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    legal_name: str
    trading_name: str | None
    description: str
    industry: str
    emirate: str
    country: str
    year_established: int
    employee_count: int
    years_of_experience: int
    trade_licence_number: str
    trade_licence_expiry: date
    licence_activities: list[str]
    website: str | None
    contact_email: str
    contact_phone: str | None
    annual_revenue_range: str | None
    preferred_contract_value_min: Decimal | None
    preferred_contract_value_max: Decimal | None
    service_categories: list[str]
    geographic_coverage: list[str]
    #: Recalculated on read from the persisted fields, so a stale stored value is never served.
    profile_completion_percentage: int
    completion: CompletionRead
    created_at: datetime
    updated_at: datetime

    @field_validator("id", mode="before")
    @classmethod
    def _stringify_id(cls, value: object) -> str:
        return str(value)
