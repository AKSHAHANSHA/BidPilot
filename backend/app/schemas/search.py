"""Natural-language search schemas (`docs/09_PORTAL_SPEC.md` §5).

The query is untrusted input. It is passed as the *user* message between the standard
`DOCUMENT_DELIMITER` markers with the injection guard on the system prompt, and it is never
interpolated into a system prompt — these bounds are the first line of that defence.

The model's only job is to turn the query into a `SearchInterpretation`. Ranking is
deterministic Python over that structure: the model never sees the listing set, so it cannot
invent a listing, and it never orders the results. The interpretation is echoed back so the UI
can show what was understood and let the user correct it.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.enums import Emirate, TenderCategory
from app.schemas.listing import ListingCard

MAX_QUERY_LENGTH = 500
MAX_KEYWORDS = 20
MAX_KEYWORD_LENGTH = 60
MAX_REASONS = 5
MAX_REASON_LENGTH = 200

#: Hard ceiling on `limit`, mirroring the upper bound of `settings.search_max_results` so the
#: published contract is fixed. The service clamps further to the configured value.
MAX_SEARCH_LIMIT = 100


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: Annotated[
        str,
        Field(
            min_length=2,
            max_length=MAX_QUERY_LENGTH,
            description=(
                'Plain language, e.g. "we do MEP fit-out in Sharjah, about 30 staff". Treated '
                "as untrusted evidence, never as instructions."
            ),
            examples=["we do MEP fit-out in Sharjah, about 30 staff"],
        ),
    ]
    limit: Annotated[
        int | None,
        Field(
            ge=1,
            le=MAX_SEARCH_LIMIT,
            description=(
                "Maximum matches to return. Omit to use the server's configured maximum; a "
                "larger value is clamped to it."
            ),
        ),
    ] = None

    @field_validator("query")
    @classmethod
    def _query_is_substantive(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 2:
            raise ValueError("A search query is required")
        return stripped


class SearchInterpretation(BaseModel):
    """What the query was understood to mean.

    `extra="forbid"` because this doubles as the structured output contract the provider must
    return: an unknown key is a malformed completion, not something to guess at. Every field
    is optional — a query that says nothing about budget must not cause the model to invent
    one.
    """

    model_config = ConfigDict(extra="forbid")

    categories: Annotated[list[TenderCategory], Field(max_length=len(TenderCategory))] = Field(
        default_factory=list
    )
    emirates: Annotated[list[Emirate], Field(max_length=len(Emirate))] = Field(default_factory=list)
    budget_min: Annotated[Decimal | None, Field(ge=0, le=Decimal("99999999999.99"))] = None
    budget_max: Annotated[Decimal | None, Field(ge=0, le=Decimal("99999999999.99"))] = None
    keywords: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=MAX_KEYWORD_LENGTH)]],
        Field(max_length=MAX_KEYWORDS),
    ] = Field(default_factory=list)

    @model_validator(mode="after")
    def _budget_band_in_order(self) -> SearchInterpretation:
        if (
            self.budget_min is not None
            and self.budget_max is not None
            and self.budget_min > self.budget_max
        ):
            raise ValueError("Interpreted minimum budget cannot exceed the maximum")
        return self


class SearchMatch(BaseModel):
    """One ranked listing, with the reasons Python scored it where it did."""

    listing: ListingCard
    score: Annotated[
        float,
        Field(
            ge=0,
            description=(
                "Deterministic relevance score computed in Python from the interpretation. "
                "Comparable within one response only."
            ),
        ),
    ]
    reasons: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=MAX_REASON_LENGTH)]],
        Field(
            max_length=MAX_REASONS,
            description='Why this listing matched, e.g. "category: Facilities Management".',
        ),
    ] = Field(default_factory=list)


class SearchResponse(BaseModel):
    interpretation: Annotated[
        SearchInterpretation,
        Field(description="What the query was understood to mean, so the user can correct it."),
    ]
    matches: list[SearchMatch]
    degraded: Annotated[
        bool,
        Field(
            description=(
                "True when no language model ran and the interpretation came from plain text "
                "processing. Search still works; it is simply less clever, and the UI says so "
                "rather than pretending a model answered."
            )
        ),
    ]
