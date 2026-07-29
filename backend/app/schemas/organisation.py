"""Organisation schemas — the identity behind every portal account, buyer or supplier.

Three read shapes exist deliberately, and which one a response uses is a security decision
rather than a convenience. `OrganisationSummary` is the only shape a public or cross-account
response may carry: it holds exactly what a listing card or an applicant row has to render.
`OrganisationRead` is the owner's own view and carries contact details, so it must never be
embedded in a response addressed to anybody else (`docs/09_PORTAL_SPEC.md` §3.1).

The summary omits the contact block by *construction*, not by a filter, so a field added to
`OrganisationRead` later cannot silently start appearing on the public feed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, field_validator

from app.domain.enums import AccountType, Emirate

MAX_DESCRIPTION_LENGTH = 4000

#: Mirrors the `year_established` CHECK constraint on `organisations`.
MIN_YEAR_ESTABLISHED = 1800
MAX_YEAR_ESTABLISHED = 2200

#: `organisations.website` is `String(255)`; `HttpUrl` on its own accepts far longer values and
#: would turn a plausible-looking sign-up into a database error at flush time.
MAX_WEBSITE_LENGTH = 255


def _strip_to_none(value: str | None) -> str | None:
    """Trim, and treat an all-whitespace value as absent rather than as an empty string."""
    if value is None:
        return None
    return value.strip() or None


class OrganisationBase(BaseModel):
    # Matches every other write schema in this package. It also makes the omission of
    # `account_type` enforceable rather than merely documented: a client that states the side
    # here as well as on the account is told so, instead of having the value silently dropped
    # and quietly disagreeing with the account it belongs to.
    model_config = ConfigDict(extra="forbid")

    name: Annotated[
        str,
        Field(
            min_length=2,
            max_length=255,
            description="Registered or trading name, shown on every listing card.",
        ),
    ]
    description: Annotated[
        str,
        Field(
            min_length=1,
            max_length=MAX_DESCRIPTION_LENGTH,
            description="What the organisation does, in its own words.",
        ),
    ]
    industry: Annotated[str | None, Field(max_length=120)] = None
    registration_number: Annotated[
        str | None,
        Field(
            max_length=100,
            description=(
                "Trade licence or commercial registration number. Free text: the format varies "
                "by emirate and by authority."
            ),
        ),
    ] = None
    emirate: Emirate
    city: Annotated[str | None, Field(max_length=120)] = None
    address_line: Annotated[str | None, Field(max_length=255)] = None
    country: Annotated[str, Field(min_length=2, max_length=100)] = "United Arab Emirates"
    contact_email: Annotated[
        EmailStr,
        Field(description="Reachable address for this organisation. Never exposed publicly."),
    ]
    contact_phone: Annotated[str | None, Field(max_length=40)] = None
    website: HttpUrl | None = None
    year_established: Annotated[
        int | None, Field(ge=MIN_YEAR_ESTABLISHED, le=MAX_YEAR_ESTABLISHED)
    ] = None
    employee_count: Annotated[int | None, Field(ge=0, le=1_000_000)] = None

    @field_validator("name", "description", "country")
    @classmethod
    def _required_text(cls, value: str) -> str:
        # `min_length` counts the padding, so "  a  " would pass a two-character minimum and
        # then be stored as a one-character name.
        stripped = value.strip()
        if not stripped:
            raise ValueError("This field must contain non-whitespace characters")
        return stripped

    @field_validator("industry", "registration_number", "city", "address_line")
    @classmethod
    def _optional_text(cls, value: str | None) -> str | None:
        return _strip_to_none(value)

    @field_validator("year_established")
    @classmethod
    def _not_in_the_future(cls, value: int | None) -> int | None:
        # Depends on the current date, so it cannot live in a database check constraint; the
        # constraint still enforces the immutable 1800-2200 bound.
        if value is None:
            return None
        current_year = datetime.now(tz=UTC).year
        if value > current_year:
            raise ValueError(f"Year established cannot be later than {current_year}")
        return value

    @field_validator("website")
    @classmethod
    def _website_fits_column(cls, value: HttpUrl | None) -> HttpUrl | None:
        if value is not None and len(str(value)) > MAX_WEBSITE_LENGTH:
            raise ValueError(f"Website URL must be at most {MAX_WEBSITE_LENGTH} characters")
        return value


class OrganisationCreate(OrganisationBase):
    """The organisation block of a registration request.

    `account_type` is absent by design: it is copied from the account being created, and
    letting a client state it in two places invites the two to disagree. `is_verified` is
    absent for the same reason it is never editable — an administrator sets it out of band.
    """


class OrganisationUpdate(BaseModel):
    """Partial update. Omitted fields are left untouched.

    `PATCH` semantics mean "unset" and "absent" must be distinguishable, which is why the
    service applies only the keys present in `model_fields_set`.
    """

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=2, max_length=255)] | None = None
    description: Annotated[str, Field(min_length=1, max_length=MAX_DESCRIPTION_LENGTH)] | None = (
        None
    )
    industry: Annotated[str | None, Field(max_length=120)] = None
    registration_number: Annotated[str | None, Field(max_length=100)] = None
    emirate: Emirate | None = None
    city: Annotated[str | None, Field(max_length=120)] = None
    address_line: Annotated[str | None, Field(max_length=255)] = None
    country: Annotated[str, Field(min_length=2, max_length=100)] | None = None
    contact_email: EmailStr | None = None
    contact_phone: Annotated[str | None, Field(max_length=40)] = None
    website: HttpUrl | None = None
    year_established: Annotated[
        int | None, Field(ge=MIN_YEAR_ESTABLISHED, le=MAX_YEAR_ESTABLISHED)
    ] = None
    employee_count: Annotated[int | None, Field(ge=0, le=1_000_000)] = None

    @field_validator("name", "description", "country")
    @classmethod
    def _required_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("This field must contain non-whitespace characters")
        return stripped

    @field_validator("industry", "registration_number", "city", "address_line")
    @classmethod
    def _optional_text(cls, value: str | None) -> str | None:
        return _strip_to_none(value)

    @field_validator("year_established")
    @classmethod
    def _not_in_the_future(cls, value: int | None) -> int | None:
        if value is None:
            return None
        current_year = datetime.now(tz=UTC).year
        if value > current_year:
            raise ValueError(f"Year established cannot be later than {current_year}")
        return value

    @field_validator("website")
    @classmethod
    def _website_fits_column(cls, value: HttpUrl | None) -> HttpUrl | None:
        if value is not None and len(str(value)) > MAX_WEBSITE_LENGTH:
            raise ValueError(f"Website URL must be at most {MAX_WEBSITE_LENGTH} characters")
        return value


class OrganisationSummary(BaseModel):
    """The small public shape shown on a listing card or an applicant row.

    Contact details and `owner_user_id` are absent by construction. This is the *only*
    organisation schema that may appear in an unauthenticated response or in a response
    addressed to the other side of the marketplace.
    """

    model_config = ConfigDict(from_attributes=True)

    name: str
    emirate: Emirate
    city: str | None
    industry: str | None
    is_verified: Annotated[
        bool,
        Field(
            description=(
                "Checked by an administrator out of band. A badge only — verification never "
                "affects a screening score."
            )
        ),
    ]
    website: str | None


class OrganisationRead(BaseModel):
    """The owner's own view, contact block included.

    Never embed this in a response addressed to anybody but the owner; use
    `OrganisationSummary` there. `owner_user_id` is omitted entirely — the owner already knows
    who they are, and nobody else may learn it.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_type: Annotated[
        AccountType,
        Field(description="Copied from the owning account at registration and never updated."),
    ]
    name: str
    description: str
    industry: str | None
    registration_number: str | None
    emirate: Emirate
    city: str | None
    address_line: str | None
    country: str
    contact_email: str
    contact_phone: str | None
    website: str | None
    year_established: int | None
    employee_count: int | None
    is_verified: bool
    created_at: datetime
    updated_at: datetime
