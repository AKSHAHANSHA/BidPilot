"""Tender listing schemas — the public catalogue contract and the buyer's editing surface.

Two read shapes, split by audience rather than by convenience. `ListingCard` is what the
public grid renders; `ListingDetail` extends it with the full brief and the document
checklist. Neither carries `owner_user_id`, and the public endpoints that serve them are
restricted to `status='published'` (`docs/09_PORTAL_SPEC.md` §3.1).

`days_remaining` and every `*_label` are derived on read. A stored `days_remaining` would be
wrong within a day of being written, and a stored label would have to be migrated every time
the wording changed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Final

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    computed_field,
    field_validator,
    model_validator,
)

from app.domain.enums import (
    Emirate,
    ListingStatus,
    RequiredDocumentType,
    TenderCategory,
)
from app.schemas.organisation import OrganisationSummary

#: Mirrors the column widths on `tender_listings`.
MAX_SUMMARY_LENGTH = 400
MAX_DESCRIPTION_LENGTH = 20000
MAX_NOTES_LENGTH = 2000
MAX_COVER_IMAGE_LENGTH = 500

MAX_TAGS = 20
MAX_TAG_LENGTH = 40
MAX_CERTIFICATIONS = 20
MAX_CERTIFICATION_LENGTH = 120

#: Money is never a float: these figures are compared against vendor bid amounts, where binary
#: rounding error is unacceptable. Bounded to fit `Numeric(14, 2)`.
Money = Annotated[Decimal, Field(ge=0, le=Decimal("99999999999.99"), decimal_places=2)]
Percentage = Annotated[Decimal, Field(ge=0, le=100, decimal_places=2)]

ShortText = Annotated[str, Field(min_length=1, max_length=MAX_TAG_LENGTH)]
Certification = Annotated[str, Field(min_length=1, max_length=MAX_CERTIFICATION_LENGTH)]
TagList = Annotated[list[ShortText], Field(max_length=MAX_TAGS)]
CertificationList = Annotated[list[Certification], Field(max_length=MAX_CERTIFICATIONS)]

#: Vocabulary values whose title-cased form reads wrong. Everything else is derived, so adding
#: a category or a document type does not mean hand-writing another label.
_LABEL_OVERRIDES: Final[dict[str, str]] = {
    "ai_data_analytics": "AI Data Analytics",
    "hr_recruitment": "HR Recruitment",
    "hse_plan": "HSE Plan",
    "iso_certification": "ISO Certification",
    "it_software": "IT Software",
    "staff_cvs": "Staff CVs",
    "vat_tax_certificate": "VAT Tax Certificate",
}


def label_for(value: str) -> str:
    """Human-readable label for a snake_case vocabulary value.

    Shared by every schema that has to show a category, a required document type, or a
    screening finding, so the same enum member never appears under two different names in the
    same interface. Accepts a `StrEnum` member as well as its raw value.
    """
    return _LABEL_OVERRIDES.get(str(value)) or str(value).replace("_", " ").title()


def _days_remaining(deadline: datetime | None) -> int | None:
    """Whole days from now until the deadline; negative once it has passed.

    Floored rather than clamped or rounded, which buys the invariant the UI actually needs:
    the value is `>= 0` if and only if the deadline is still in the future, so a listing that
    closed an hour ago reads as -1 and can never be rendered as "closes today".
    """
    if deadline is None:
        return None
    # The column is `DateTime(timezone=True)`, but a naive value would raise on subtraction and
    # turn an ordinary read into a 500. Treating it as UTC degrades to a wrong-by-hours figure
    # instead of a broken page.
    reference = deadline if deadline.tzinfo is not None else deadline.replace(tzinfo=UTC)
    return (reference - datetime.now(tz=UTC)).days


def _clean_items(values: list[str]) -> list[str]:
    """Trim, drop blanks, de-duplicate case-insensitively, keep order and original casing.

    Case is preserved because these strings are displayed — "ISO 9001" must not become
    "iso 9001" — but de-duplication is case-insensitive so "MEP" and "mep" cannot survive as
    two distinct tags and split a search result.
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


def _require_aware(value: datetime | None) -> datetime | None:
    # A naive deadline cannot be compared against now() for the closing job or the countdown.
    if value is not None and value.tzinfo is None:
        raise ValueError("Deadlines must include a timezone offset")
    return value


def _validate_cover_image(value: str | None) -> str | None:
    url = value.strip() if value is not None else None
    if not url:
        return None
    # Rendered straight into an <img src>. Anything that is not http(s) or site-relative is
    # either inert or a payload, and neither is a cover image.
    if not url.startswith(("/", "http://", "https://")):
        raise ValueError("Cover image URL must be an absolute http(s) URL or a site-relative path")
    return url


# --- Document requirements ----------------------------------------------------------------


class DocumentRequirementWrite(BaseModel):
    """One checklist entry as the buyer submits it.

    `display_order` is absent deliberately: the order of the list in the request body *is* the
    display order, so a body cannot carry an arrangement that contradicts itself.
    """

    model_config = ConfigDict(extra="forbid")

    document_type: RequiredDocumentType
    is_mandatory: Annotated[
        bool,
        Field(
            description="Mandatory items gate the submission; optional ones only move the score."
        ),
    ] = True
    weight: Annotated[
        int,
        Field(
            ge=1,
            le=10,
            description=(
                "Relative importance within the mandatory or optional band. Bounded so one "
                "requirement cannot dominate the whole score."
            ),
        ),
    ] = 1
    notes: Annotated[
        str | None,
        Field(
            max_length=MAX_NOTES_LENGTH,
            description='The buyer\'s own wording, e.g. "valid for 90 days beyond closing".',
        ),
    ] = None

    @field_validator("notes")
    @classmethod
    def _strip_notes(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value is not None else None


class RequirementChecklistWrite(RootModel[list[DocumentRequirementWrite]]):
    """`PUT /listings/{id}/requirements` — the whole checklist, replaced wholesale.

    A bare array rather than an object because the list *is* the checklist: partial edits
    would need per-row identity, and replacing the set outright is both simpler to reason
    about and the only way to express "this requirement is gone".
    """

    # One row per document type at most — the same rule the unique constraint on
    # `listing_document_requirements` enforces, so a longer list is always a client mistake.
    root: Annotated[list[DocumentRequirementWrite], Field(max_length=len(RequiredDocumentType))]

    @model_validator(mode="after")
    def _no_duplicate_document_types(self) -> RequirementChecklistWrite:
        seen: set[str] = set()
        for requirement in self.root:
            if requirement.document_type in seen:
                raise ValueError(
                    f"Duplicate document requirement: {label_for(requirement.document_type)}"
                )
            seen.add(requirement.document_type)
        return self


class DocumentRequirementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_type: RequiredDocumentType
    is_mandatory: bool
    weight: int
    notes: str | None
    display_order: int

    @computed_field(description="Human-readable form of `document_type`.")  # type: ignore[prop-decorator]
    @property
    def label(self) -> str:
        return label_for(self.document_type)


# --- Write shapes -------------------------------------------------------------------------


class ListingBase(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=255)]
    summary: Annotated[
        str,
        Field(
            min_length=1,
            max_length=MAX_SUMMARY_LENGTH,
            description=(
                "One-paragraph pitch for the catalogue card. Separate from `description` so a "
                "card never truncates arbitrary prose mid-sentence."
            ),
        ),
    ]
    description: Annotated[str, Field(min_length=1, max_length=MAX_DESCRIPTION_LENGTH)]
    category: TenderCategory
    industry: Annotated[
        str | None,
        Field(
            max_length=120,
            description=(
                'Free-text refinement under the controlled category, e.g. "district cooling".'
            ),
        ),
    ] = None
    reference: Annotated[
        str | None,
        Field(
            max_length=120,
            description="The buyer's own tender reference. Unique within their organisation.",
        ),
    ] = None
    tags: TagList = Field(default_factory=list)
    emirate: Emirate
    city: Annotated[str | None, Field(max_length=120)] = None
    budget_min: Money | None = None
    budget_max: Money | None = None
    currency: Annotated[str, Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")] = "AED"
    submission_deadline: Annotated[
        datetime | None,
        Field(description="Required before the listing can be published; optional on a draft."),
    ] = None
    questions_deadline: datetime | None = None
    contract_duration_months: Annotated[int | None, Field(ge=1, le=600)] = None
    min_years_experience: Annotated[int | None, Field(ge=0, le=200)] = None
    required_certifications: CertificationList = Field(default_factory=list)
    requires_bid_bond: bool = False
    bid_bond_percentage: Percentage | None = None
    cover_image_url: Annotated[str | None, Field(max_length=MAX_COVER_IMAGE_LENGTH)] = None

    @field_validator("title", "summary", "description")
    @classmethod
    def _required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("This field must contain non-whitespace characters")
        return stripped

    @field_validator("industry", "reference", "city")
    @classmethod
    def _optional_text(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value is not None else None

    @field_validator("tags", "required_certifications")
    @classmethod
    def _normalize_lists(cls, value: list[str]) -> list[str]:
        return _clean_items(value)

    @field_validator("submission_deadline", "questions_deadline")
    @classmethod
    def _deadlines_are_aware(cls, value: datetime | None) -> datetime | None:
        return _require_aware(value)

    @field_validator("cover_image_url")
    @classmethod
    def _cover_image_is_safe(cls, value: str | None) -> str | None:
        return _validate_cover_image(value)

    @model_validator(mode="after")
    def _validate_relationships(self) -> ListingBase:
        if (
            self.budget_min is not None
            and self.budget_max is not None
            and self.budget_min > self.budget_max
        ):
            raise ValueError("Minimum budget cannot exceed the maximum budget")
        if (
            self.questions_deadline is not None
            and self.submission_deadline is not None
            and self.questions_deadline > self.submission_deadline
        ):
            raise ValueError("The questions deadline cannot be later than the submission deadline")
        # A bid bond percentage with no bid bond required is a contradiction the vendor would
        # have to guess at.
        if self.bid_bond_percentage is not None and not self.requires_bid_bond:
            raise ValueError("A bid bond percentage requires requires_bid_bond to be true")
        return self


class ListingCreate(ListingBase):
    """A new listing. Always created as a draft — `status` and `published_at` are set by the
    publish transition, never by the client."""


class ListingUpdate(BaseModel):
    """Partial update. Omitted fields are left untouched.

    `status` is absent: the lifecycle moves through `/publish` and `/close`, which can enforce
    their preconditions. A PATCHable status would let a listing be published without a
    deadline or reopened after applicants had been told it closed.
    """

    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    summary: Annotated[str, Field(min_length=1, max_length=MAX_SUMMARY_LENGTH)] | None = None
    description: Annotated[str, Field(min_length=1, max_length=MAX_DESCRIPTION_LENGTH)] | None = (
        None
    )
    category: TenderCategory | None = None
    industry: Annotated[str | None, Field(max_length=120)] = None
    reference: Annotated[str | None, Field(max_length=120)] = None
    tags: TagList | None = None
    emirate: Emirate | None = None
    city: Annotated[str | None, Field(max_length=120)] = None
    budget_min: Money | None = None
    budget_max: Money | None = None
    currency: Annotated[str, Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")] | None = None
    submission_deadline: datetime | None = None
    questions_deadline: datetime | None = None
    contract_duration_months: Annotated[int | None, Field(ge=1, le=600)] = None
    min_years_experience: Annotated[int | None, Field(ge=0, le=200)] = None
    required_certifications: CertificationList | None = None
    requires_bid_bond: bool | None = None
    bid_bond_percentage: Percentage | None = None
    cover_image_url: Annotated[str | None, Field(max_length=MAX_COVER_IMAGE_LENGTH)] = None

    @field_validator("title", "summary", "description")
    @classmethod
    def _required_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("This field must contain non-whitespace characters")
        return stripped

    @field_validator("industry", "reference", "city")
    @classmethod
    def _optional_text(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value is not None else None

    @field_validator("tags", "required_certifications")
    @classmethod
    def _normalize_lists(cls, value: list[str] | None) -> list[str] | None:
        return _clean_items(value) if value is not None else None

    @field_validator("submission_deadline", "questions_deadline")
    @classmethod
    def _deadlines_are_aware(cls, value: datetime | None) -> datetime | None:
        return _require_aware(value)

    @field_validator("cover_image_url")
    @classmethod
    def _cover_image_is_safe(cls, value: str | None) -> str | None:
        return _validate_cover_image(value)

    @model_validator(mode="after")
    def _validate_partial_relationships(self) -> ListingUpdate:
        # Only checkable when both halves arrive together; a one-sided update is validated
        # against the persisted row in the service, which can see the other half.
        if (
            self.budget_min is not None
            and self.budget_max is not None
            and self.budget_min > self.budget_max
        ):
            raise ValueError("Minimum budget cannot exceed the maximum budget")
        if (
            self.questions_deadline is not None
            and self.submission_deadline is not None
            and self.questions_deadline > self.submission_deadline
        ):
            raise ValueError("The questions deadline cannot be later than the submission deadline")
        if self.bid_bond_percentage is not None and self.requires_bid_bond is False:
            raise ValueError("A bid bond percentage requires requires_bid_bond to be true")
        return self


# --- Read shapes --------------------------------------------------------------------------


class ListingCard(BaseModel):
    """One item in the public catalogue grid.

    Everything here is safe for an unauthenticated caller: no owner identity, no applicant
    identities, no buyer contact details.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    summary: str
    category: TenderCategory
    emirate: Emirate
    city: str | None
    budget_min: Decimal | None
    budget_max: Decimal | None
    currency: str
    submission_deadline: datetime | None
    cover_image_url: str | None
    application_count: Annotated[
        int,
        Field(
            description="Applications received so far. A denormalised counter, not a live count."
        ),
    ]
    tags: list[str]
    organisation: OrganisationSummary

    @computed_field(description="Human-readable form of `category`.")  # type: ignore[prop-decorator]
    @property
    def category_label(self) -> str:
        return label_for(self.category)

    @computed_field(  # type: ignore[prop-decorator]
        description=(
            "Whole days until the submission deadline. Negative once it has passed, null when "
            "the listing has no deadline. Derived on every read, never stored."
        )
    )
    @property
    def days_remaining(self) -> int | None:
        return _days_remaining(self.submission_deadline)


class ListingDetail(ListingCard):
    """The full public brief: everything on the card plus the terms and the checklist."""

    description: str
    reference: str | None
    industry: str | None
    questions_deadline: datetime | None
    contract_duration_months: int | None
    min_years_experience: int | None
    required_certifications: list[str]
    requires_bid_bond: bool
    bid_bond_percentage: Decimal | None
    published_at: datetime | None
    status: ListingStatus
    document_requirements: list[DocumentRequirementRead]


# --- Aggregates ---------------------------------------------------------------------------


class CategoryCount(BaseModel):
    """One row of `GET /public/categories`.

    Categories with no published listings are still returned — the landing page renders the
    whole taxonomy, and a category that vanished when its last listing closed would make the
    navigation flicker.
    """

    category: TenderCategory
    count: Annotated[int, Field(ge=0, description="Published listings in this category.")]

    @computed_field(description="Human-readable form of `category`.")  # type: ignore[prop-decorator]
    @property
    def label(self) -> str:
        return label_for(self.category)


class PortalStats(BaseModel):
    """Hero counters for the landing page. Published listings only."""

    published_listings: Annotated[int, Field(ge=0)]
    buying_organisations: Annotated[
        int, Field(ge=0, description="Distinct organisations with at least one published listing.")
    ]
    total_published_value: Annotated[
        Decimal,
        Field(
            ge=0,
            description=(
                "Sum of the disclosed maximum budget across published listings. Listings that "
                "do not disclose a budget contribute nothing rather than an estimate."
            ),
        ),
    ]
    currency: Annotated[
        str,
        Field(
            min_length=3,
            max_length=3,
            description="Currency `total_published_value` is expressed in.",
        ),
    ] = "AED"
    active_categories: Annotated[
        int,
        Field(
            ge=0,
            description="Distinct categories with at least one published listing.",
        ),
    ]
