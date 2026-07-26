"""Deterministic company-profile completion scoring.

Calculated in Python from the profile's own fields — never by the frontend, never by a model.
Isolated in this module and versioned so the weights can change without touching routes,
services, or the schema.

**Why the score depends only on the profile row.** Evidence and project counts were considered
and rejected: cross-entity inputs would mean the score changes without the profile being
written, which is the same staleness trap that expiry state avoids by never being stored.
Keeping the inputs local means the stored value is correct the moment it is written.

**Bounded by construction.** The weights sum to exactly 100 (asserted at import and in a unit
test), each rule contributes its whole weight or nothing, and the total is the sum of earned
weights. There is no arithmetic path to a value outside 0-100.

**Three groups, and how each behaves:**

* *Core* (78) — the fields the API requires at creation. A profile that exists earns most of
  these, but text fields must be substantive: a one-word description earns nothing, because the
  point of the score is to signal readiness, not to congratulate an empty shell.
* *Depth* (10) — rewards richer arrays. One service category is enough to save a profile;
  three describe a business well enough to match tender scope against.
* *Commercial* (12) — the fields marked optional in the specification. They are what moves a
  serviceable profile to 100.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

#: Bump when weights or rules change. Stored alongside the score so an old value is
#: identifiable after the algorithm moves on.
COMPLETION_VERSION = "1.0.0"

#: A description shorter than this is treated as absent. Chosen to exclude placeholders like
#: "FM company" while accepting a genuine one-sentence summary.
MIN_DESCRIPTION_LENGTH = 40

MAX_SCORE = 100


class ProfileLike(Protocol):
    """Structural type of what scoring needs.

    A Protocol rather than the ORM model so the rules can be unit-tested against plain objects
    and so this module does not import the persistence layer.
    """

    legal_name: str
    trading_name: str | None
    description: str
    industry: str
    emirate: str
    country: str
    year_established: int
    employee_count: int
    trade_licence_number: str
    trade_licence_expiry: Any
    website: str | None
    contact_email: str
    contact_phone: str | None
    annual_revenue_range: str | None
    preferred_contract_value_min: Decimal | None
    preferred_contract_value_max: Decimal | None
    years_of_experience: int

    # Read-only members, so a `list[str]` attribute on the ORM model satisfies the protocol.
    # A mutable `Sequence[str]` attribute would be invariant and reject `list[str]`.
    @property
    def licence_activities(self) -> Sequence[str]: ...

    @property
    def service_categories(self) -> Sequence[str]: ...

    @property
    def geographic_coverage(self) -> Sequence[str]: ...


@dataclass(frozen=True, slots=True)
class CompletionRule:
    key: str
    label: str
    weight: int
    group: str
    hint: str
    earned: Callable[[ProfileLike], bool]


def _text(value: str | None, *, minimum: int = 1) -> bool:
    return value is not None and len(value.strip()) >= minimum


def _items(value: Sequence[str] | None, *, minimum: int = 1) -> bool:
    if not value:
        return False
    return len([item for item in value if item and item.strip()]) >= minimum


CORE = "core"
DEPTH = "depth"
COMMERCIAL = "commercial"

RULES: tuple[CompletionRule, ...] = (
    # --- Core identity and licence (78) ---
    CompletionRule(
        key="legal_name",
        label="Legal company name",
        weight=6,
        group=CORE,
        hint="The name on the trade licence.",
        earned=lambda p: _text(p.legal_name),
    ),
    CompletionRule(
        key="description",
        label="Company description",
        weight=8,
        group=CORE,
        hint=f"At least {MIN_DESCRIPTION_LENGTH} characters describing what the company does.",
        earned=lambda p: _text(p.description, minimum=MIN_DESCRIPTION_LENGTH),
    ),
    CompletionRule(
        key="industry",
        label="Industry",
        weight=5,
        group=CORE,
        hint="Primary industry, e.g. facilities management.",
        earned=lambda p: _text(p.industry),
    ),
    CompletionRule(
        key="emirate",
        label="Emirate",
        weight=4,
        group=CORE,
        hint="Where the company is licensed.",
        earned=lambda p: _text(p.emirate),
    ),
    CompletionRule(
        key="country",
        label="Country",
        weight=3,
        group=CORE,
        hint="Country of registration.",
        earned=lambda p: _text(p.country),
    ),
    CompletionRule(
        key="year_established",
        label="Year established",
        weight=4,
        group=CORE,
        hint="Used to sanity-check claimed experience.",
        earned=lambda p: bool(p.year_established),
    ),
    CompletionRule(
        key="employee_count",
        label="Employee count",
        weight=4,
        group=CORE,
        hint="Tenders often set a minimum headcount.",
        earned=lambda p: p.employee_count > 0,
    ),
    CompletionRule(
        key="trade_licence_number",
        label="Trade licence number",
        weight=7,
        group=CORE,
        hint="Mandatory for almost every UAE tender.",
        earned=lambda p: _text(p.trade_licence_number),
    ),
    CompletionRule(
        key="trade_licence_expiry",
        label="Trade licence expiry",
        weight=5,
        group=CORE,
        hint="A licence expiring before the contract start is a hard blocker.",
        earned=lambda p: p.trade_licence_expiry is not None,
    ),
    CompletionRule(
        key="licence_activities",
        label="Licence activities",
        weight=7,
        group=CORE,
        hint="Tender scope is checked against licensed activities.",
        earned=lambda p: _items(p.licence_activities),
    ),
    CompletionRule(
        key="contact_email",
        label="Contact email",
        weight=5,
        group=CORE,
        hint="Where submission correspondence goes.",
        earned=lambda p: _text(p.contact_email),
    ),
    CompletionRule(
        key="service_categories",
        label="Service categories",
        weight=8,
        group=CORE,
        hint="The services the company can actually deliver.",
        earned=lambda p: _items(p.service_categories),
    ),
    CompletionRule(
        key="geographic_coverage",
        label="Geographic coverage",
        weight=7,
        group=CORE,
        hint="Tenders frequently restrict bidders by location.",
        earned=lambda p: _items(p.geographic_coverage),
    ),
    CompletionRule(
        key="years_of_experience",
        label="Years of operating experience",
        weight=5,
        group=CORE,
        hint="Compared against minimum-experience requirements.",
        earned=lambda p: p.years_of_experience > 0,
    ),
    # --- Depth of the list fields (10) ---
    CompletionRule(
        key="licence_activities_detail",
        label="Three or more licence activities",
        weight=3,
        group=DEPTH,
        hint="Listing every licensed activity widens the tenders you qualify for.",
        earned=lambda p: _items(p.licence_activities, minimum=3),
    ),
    CompletionRule(
        key="service_categories_detail",
        label="Three or more service categories",
        weight=4,
        group=DEPTH,
        hint="More categories give requirement matching more to work with.",
        earned=lambda p: _items(p.service_categories, minimum=3),
    ),
    CompletionRule(
        key="geographic_coverage_detail",
        label="Two or more covered locations",
        weight=3,
        group=DEPTH,
        hint="Add every emirate or region you can service.",
        earned=lambda p: _items(p.geographic_coverage, minimum=2),
    ),
    # --- Optional commercial detail (12) ---
    CompletionRule(
        key="trading_name",
        label="Trading name",
        weight=2,
        group=COMMERCIAL,
        hint="If the company trades under a different name.",
        earned=lambda p: _text(p.trading_name),
    ),
    CompletionRule(
        key="website",
        label="Website",
        weight=2,
        group=COMMERCIAL,
        hint="Buyers check it during evaluation.",
        earned=lambda p: _text(p.website),
    ),
    CompletionRule(
        key="contact_phone",
        label="Contact phone",
        weight=2,
        group=COMMERCIAL,
        hint="Some portals require a phone number.",
        earned=lambda p: _text(p.contact_phone),
    ),
    CompletionRule(
        key="annual_revenue_range",
        label="Annual revenue range",
        weight=2,
        group=COMMERCIAL,
        hint="Used against financial-capacity requirements.",
        earned=lambda p: _text(p.annual_revenue_range),
    ),
    CompletionRule(
        key="preferred_contract_value",
        label="Preferred contract value range",
        weight=4,
        group=COMMERCIAL,
        hint="Both a minimum and a maximum, so oversized tenders can be flagged early.",
        earned=lambda p: (
            p.preferred_contract_value_min is not None
            and p.preferred_contract_value_max is not None
        ),
    ),
)

TOTAL_WEIGHT = sum(rule.weight for rule in RULES)

# A weight edit that breaks the 0-100 guarantee fails at import rather than silently producing
# out-of-range scores. A raise rather than an assert, so `python -O` cannot skip the check.
if TOTAL_WEIGHT != MAX_SCORE:  # pragma: no cover - configuration error, not a runtime path
    raise RuntimeError(
        f"Completion weights must total {MAX_SCORE}, got {TOTAL_WEIGHT}. "
        "Adjust RULES so the score stays bounded."
    )


@dataclass(frozen=True, slots=True)
class CompletionComponent:
    key: str
    label: str
    group: str
    weight: int
    earned: bool
    hint: str


@dataclass(frozen=True, slots=True)
class CompletionResult:
    score: int
    version: str
    components: tuple[CompletionComponent, ...]

    @property
    def missing(self) -> tuple[CompletionComponent, ...]:
        """Unearned components, heaviest first — the frontend's "what to do next" list."""
        return tuple(
            sorted(
                (c for c in self.components if not c.earned),
                key=lambda c: c.weight,
                reverse=True,
            )
        )


def calculate_completion(profile: ProfileLike) -> CompletionResult:
    """Score a profile out of 100. Deterministic: same input, same output, always."""
    components = tuple(
        CompletionComponent(
            key=rule.key,
            label=rule.label,
            group=rule.group,
            weight=rule.weight,
            earned=bool(rule.earned(profile)),
            hint=rule.hint,
        )
        for rule in RULES
    )
    score = sum(component.weight for component in components if component.earned)
    return CompletionResult(score=score, version=COMPLETION_VERSION, components=components)
