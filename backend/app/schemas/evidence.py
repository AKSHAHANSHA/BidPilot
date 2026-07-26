"""Company evidence schemas, including the derived expiry view."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.enums import EvidenceCategory, ExpiryState, VerificationStatus

MAX_DESCRIPTION_LENGTH = 4000
MAX_TAGS = 20
MAX_TAG_LENGTH = 40

Tag = Annotated[str, Field(min_length=1, max_length=MAX_TAG_LENGTH)]
TagList = Annotated[list[Tag], Field(max_length=MAX_TAGS)]


def _normalize_tags(values: list[str]) -> list[str]:
    """Lower-cased, trimmed, de-duplicated, order preserved.

    Tags are a filter dimension; "ISO", "iso", and " iso " must be one tag or filtering by tag
    quietly misses records.
    """
    seen: set[str] = set()
    cleaned: list[str] = []
    for value in values:
        tag = value.strip().casefold()
        if tag and tag not in seen:
            seen.add(tag)
            cleaned.append(tag)
    return cleaned


class EvidenceBase(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=255)]
    category: EvidenceCategory
    issuing_organisation: Annotated[str | None, Field(max_length=255)] = None
    reference_number: Annotated[str | None, Field(max_length=120)] = None
    description: Annotated[str, Field(min_length=1, max_length=MAX_DESCRIPTION_LENGTH)]
    issue_date: date | None = None
    expiry_date: date | None = None
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    verification_notes: Annotated[str | None, Field(max_length=MAX_DESCRIPTION_LENGTH)] = None
    tags: TagList = Field(default_factory=list)

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, value: list[str]) -> list[str]:
        return _normalize_tags(value)

    @field_validator("title", "issuing_organisation", "reference_number")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def _dates_in_order(self) -> EvidenceBase:
        if (
            self.issue_date is not None
            and self.expiry_date is not None
            and self.expiry_date < self.issue_date
        ):
            raise ValueError("Expiry date cannot be earlier than the issue date")
        return self


class EvidenceCreate(EvidenceBase):
    pass


class EvidenceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    category: EvidenceCategory | None = None
    issuing_organisation: Annotated[str | None, Field(max_length=255)] = None
    reference_number: Annotated[str | None, Field(max_length=120)] = None
    description: Annotated[str, Field(min_length=1, max_length=MAX_DESCRIPTION_LENGTH)] | None = (
        None
    )
    issue_date: date | None = None
    expiry_date: date | None = None
    verification_status: VerificationStatus | None = None
    verification_notes: Annotated[str | None, Field(max_length=MAX_DESCRIPTION_LENGTH)] = None
    tags: TagList | None = None

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, value: list[str] | None) -> list[str] | None:
        return _normalize_tags(value) if value is not None else None

    @model_validator(mode="after")
    def _dates_in_order(self) -> EvidenceUpdate:
        # Only checkable when both dates arrive together; a one-sided update is validated
        # against the persisted value in the service.
        if (
            self.issue_date is not None
            and self.expiry_date is not None
            and self.expiry_date < self.issue_date
        ):
            raise ValueError("Expiry date cannot be earlier than the issue date")
        return self


class EvidenceExpiry(BaseModel):
    """Derived expiry view. Calculated on every read — never persisted."""

    state: ExpiryState
    days_until_expiry: int | None = Field(
        default=None,
        description="Negative when already expired; null when the evidence has no expiry date.",
    )
    threshold_days: int = Field(description="The 'expiring soon' window used for this response.")


class EvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_profile_id: str
    title: str
    category: str
    issuing_organisation: str | None
    reference_number: str | None
    description: str
    issue_date: date | None
    expiry_date: date | None
    verification_status: str
    verification_notes: str | None
    tags: list[str]
    expiry: EvidenceExpiry
    #: Always null in Phase 2. Present so the frontend contract does not change when Phase 3
    #: adds real uploads; no storage columns exist yet because adding them later is additive.
    attachment: None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("id", "company_profile_id", mode="before")
    @classmethod
    def _stringify(cls, value: object) -> str:
        return str(value)
