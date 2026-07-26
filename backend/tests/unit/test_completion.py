"""Profile completion must be deterministic, bounded, and explainable."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal

import pytest

from app.domain.completion import (
    COMPLETION_VERSION,
    MAX_SCORE,
    MIN_DESCRIPTION_LENGTH,
    RULES,
    TOTAL_WEIGHT,
    calculate_completion,
)


@dataclass
class FakeProfile:
    """A plain stand-in for the ORM model — scoring depends only on the Protocol's fields."""

    legal_name: str = "Al Mirqab Integrated Facilities Management LLC"
    trading_name: str | None = None
    description: str = "A" * MIN_DESCRIPTION_LENGTH
    industry: str = "Facilities Management"
    emirate: str = "dubai"
    country: str = "United Arab Emirates"
    year_established: int = 2011
    employee_count: int = 84
    trade_licence_number: str = "DED-000-DEMO-4471"
    trade_licence_expiry: date | None = date(2027, 1, 1)
    licence_activities: list[str] = field(default_factory=lambda: ["Cleaning"])
    website: str | None = None
    contact_email: str = "tenders@fm-demo.ae"
    contact_phone: str | None = None
    annual_revenue_range: str | None = None
    preferred_contract_value_min: Decimal | None = None
    preferred_contract_value_max: Decimal | None = None
    service_categories: list[str] = field(default_factory=lambda: ["Hard FM"])
    geographic_coverage: list[str] = field(default_factory=lambda: ["Dubai"])
    years_of_experience: int = 14


def fully_complete() -> FakeProfile:
    return FakeProfile(
        trading_name="Al Mirqab FM",
        licence_activities=["Cleaning", "HVAC", "Pest control"],
        website="https://almirqab-fm.example.ae",
        contact_phone="+971 4 000 0000",
        annual_revenue_range="5m_to_20m_aed",
        preferred_contract_value_min=Decimal("500000.00"),
        preferred_contract_value_max=Decimal("12000000.00"),
        service_categories=["Hard FM", "Soft FM", "HVAC maintenance"],
        geographic_coverage=["Dubai", "Sharjah"],
    )


# --- Structural guarantees ----------------------------------------------------------------


def test_weights_total_exactly_one_hundred() -> None:
    # The 0-100 guarantee is arithmetic, not clamping. If this fails, the module raises on
    # import and no score can be produced at all.
    assert TOTAL_WEIGHT == MAX_SCORE


def test_rule_keys_are_unique() -> None:
    keys = [rule.key for rule in RULES]
    assert len(keys) == len(set(keys))


def test_every_rule_has_a_positive_weight_and_a_hint() -> None:
    for rule in RULES:
        assert rule.weight > 0, rule.key
        assert rule.hint, rule.key


# --- Determinism and bounds ---------------------------------------------------------------


def test_same_input_always_produces_the_same_score() -> None:
    profile = fully_complete()
    scores = {calculate_completion(profile).score for _ in range(10)}
    assert scores == {MAX_SCORE}


def test_complete_profile_scores_one_hundred() -> None:
    result = calculate_completion(fully_complete())
    assert result.score == MAX_SCORE
    assert result.missing == ()
    assert result.version == COMPLETION_VERSION


def test_score_never_exceeds_one_hundred_or_drops_below_zero() -> None:
    for profile in (fully_complete(), FakeProfile(), FakeProfile(legal_name="", description="")):
        assert 0 <= calculate_completion(profile).score <= MAX_SCORE


def test_minimal_valid_profile_scores_below_complete() -> None:
    """A profile with only the required fields is serviceable but not finished."""
    result = calculate_completion(FakeProfile())
    assert 0 < result.score < MAX_SCORE
    assert result.missing  # there is always something to suggest


# --- Individual rule behaviour ------------------------------------------------------------


def test_short_description_earns_nothing() -> None:
    baseline = calculate_completion(FakeProfile()).score
    short = calculate_completion(FakeProfile(description="FM company")).score
    weight = next(rule.weight for rule in RULES if rule.key == "description")
    assert baseline - short == weight


def test_whitespace_only_text_does_not_count_as_present() -> None:
    filled = calculate_completion(FakeProfile()).score
    blank = calculate_completion(FakeProfile(legal_name="   ")).score
    assert blank < filled


def test_zero_employee_count_earns_nothing() -> None:
    # Zero is a valid stored value (the column allows it) but it is not usable evidence of scale.
    assert (
        calculate_completion(FakeProfile(employee_count=0)).score
        < calculate_completion(FakeProfile(employee_count=1)).score
    )


def test_array_depth_is_rewarded_separately_from_presence() -> None:
    """One entry saves the core rule; three earn the depth bonus as well."""
    one = calculate_completion(FakeProfile(service_categories=["Hard FM"]))
    three = calculate_completion(
        FakeProfile(service_categories=["Hard FM", "Soft FM", "HVAC maintenance"])
    )
    depth_weight = next(rule.weight for rule in RULES if rule.key == "service_categories_detail")
    assert three.score - one.score == depth_weight


def test_empty_arrays_lose_both_the_core_and_depth_weights() -> None:
    full = calculate_completion(
        FakeProfile(service_categories=["Hard FM", "Soft FM", "HVAC maintenance"])
    ).score
    empty = calculate_completion(FakeProfile(service_categories=[])).score
    core = next(rule.weight for rule in RULES if rule.key == "service_categories")
    depth = next(rule.weight for rule in RULES if rule.key == "service_categories_detail")
    assert full - empty == core + depth


def test_blank_array_entries_are_not_counted() -> None:
    assert (
        calculate_completion(FakeProfile(service_categories=["", "   "])).score
        < calculate_completion(FakeProfile(service_categories=["Hard FM"])).score
    )


def test_contract_range_needs_both_bounds() -> None:
    """Half a range cannot flag an oversized tender, so half earns nothing."""
    weight = next(rule.weight for rule in RULES if rule.key == "preferred_contract_value")
    baseline = calculate_completion(FakeProfile()).score
    only_min = calculate_completion(
        FakeProfile(preferred_contract_value_min=Decimal("500000"))
    ).score
    both = calculate_completion(
        FakeProfile(
            preferred_contract_value_min=Decimal("500000"),
            preferred_contract_value_max=Decimal("1200000"),
        )
    ).score
    assert only_min == baseline
    assert both - baseline == weight


@pytest.mark.parametrize(
    "commercial_field",
    ["trading_name", "website", "contact_phone", "annual_revenue_range"],
)
def test_each_optional_commercial_field_adds_its_weight(commercial_field: str) -> None:
    baseline = calculate_completion(FakeProfile())
    improved = calculate_completion(replace(FakeProfile(), **{commercial_field: "a value"}))
    weight = next(rule.weight for rule in RULES if rule.key == commercial_field)
    assert improved.score - baseline.score == weight


# --- Explainability ------------------------------------------------------------------------


def test_components_cover_every_rule_and_report_earned_state() -> None:
    result = calculate_completion(FakeProfile())
    assert len(result.components) == len(RULES)
    assert {c.key for c in result.components} == {rule.key for rule in RULES}
    assert any(c.earned for c in result.components)
    assert any(not c.earned for c in result.components)


def test_missing_components_are_ordered_heaviest_first() -> None:
    """The frontend shows this as "what to do next", so the biggest win comes first."""
    missing = calculate_completion(FakeProfile()).missing
    weights = [component.weight for component in missing]
    assert weights == sorted(weights, reverse=True)
    assert all(not component.earned for component in missing)


def test_score_equals_the_sum_of_earned_component_weights() -> None:
    result = calculate_completion(FakeProfile(trading_name="Al Mirqab FM"))
    assert result.score == sum(c.weight for c in result.components if c.earned)
