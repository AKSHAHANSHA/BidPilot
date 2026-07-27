"""Deterministic readiness scoring: determinism, bounds, hard blockers, labels."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.enums import ComplianceStatus, DecisionLabel
from app.domain.scoring import (
    SCORING_VERSION,
    WEIGHTS,
    RequirementScore,
    RiskScore,
    ScoringInput,
    calculate_readiness,
)


def req(category: str, status: str, *, obligation: str = "mandatory", expected=0, satisfied=0):
    return RequirementScore(
        category=category,
        obligation=obligation,
        status=status,
        expected_evidence_count=expected,
        satisfied_evidence_count=satisfied,
    )


def strong_inputs(**overrides) -> ScoringInput:
    base = {
        "requirements": [
            req("legal_registration", ComplianceStatus.MET.value),
            req("certification", ComplianceStatus.MET.value),
            req("technical_capability", ComplianceStatus.MET.value),
            req("experience", ComplianceStatus.MET.value),
        ],
        "risks": [],
        "submission_deadline": datetime.now(tz=UTC) + timedelta(days=30),
        "deadline_feasibility_days": 30,
        "bid_bond_available": None,
    }
    base.update(overrides)
    return ScoringInput(**base)


# --- Structural guarantees -----------------------------------------------------------------


def test_weights_total_one_hundred() -> None:
    assert sum(WEIGHTS.values()) == 100


def test_scoring_is_deterministic() -> None:
    data = strong_inputs()
    scores = {calculate_readiness(data).overall_score for _ in range(10)}
    assert len(scores) == 1


def test_score_stays_within_bounds() -> None:
    for data in (
        strong_inputs(),
        strong_inputs(requirements=[]),
        strong_inputs(
            requirements=[req("legal_registration", ComplianceStatus.NOT_MET.value)],
            risks=[RiskScore("critical", "liquidated_damages") for _ in range(10)],
            deadline_feasibility_days=0,
        ),
    ):
        result = calculate_readiness(data)
        assert 0 <= result.overall_score <= 100
        for dim in result.dimensions:
            assert 0 <= dim.raw_score <= 100


def test_version_is_reported() -> None:
    assert calculate_readiness(strong_inputs()).version == SCORING_VERSION


def test_dimensions_cover_all_weights() -> None:
    result = calculate_readiness(strong_inputs())
    assert {d.key for d in result.dimensions} == set(WEIGHTS)
    assert round(sum(d.weighted_score for d in result.dimensions), 1) == result.overall_score


# --- Labels --------------------------------------------------------------------------------


def test_strong_profile_is_strong_bid() -> None:
    result = calculate_readiness(strong_inputs())
    assert result.overall_score >= 80
    assert result.decision_label is DecisionLabel.STRONG_BID


def test_no_requirements_is_insufficient_information() -> None:
    result = calculate_readiness(strong_inputs(requirements=[]))
    assert result.decision_label is DecisionLabel.INSUFFICIENT_INFORMATION


# --- Hard blockers -------------------------------------------------------------------------


def test_passed_deadline_is_a_hard_blocker_and_do_not_bid() -> None:
    result = calculate_readiness(
        strong_inputs(
            submission_deadline=datetime.now(tz=UTC) - timedelta(days=1),
            deadline_feasibility_days=-1,
        )
    )
    assert any(b.code == "deadline_passed" for b in result.hard_blockers)
    # A passed deadline is never remediable → do_not_bid regardless of the numeric score.
    assert result.decision_label is DecisionLabel.DO_NOT_BID


def test_unmet_mandatory_certification_blocks() -> None:
    result = calculate_readiness(
        strong_inputs(
            requirements=[
                req("certification", ComplianceStatus.NOT_MET.value),
                req("technical_capability", ComplianceStatus.MET.value),
            ],
            deadline_feasibility_days=5,  # too soon to remediate
        )
    )
    assert any(b.code == "mandatory_eligibility_unmet" for b in result.hard_blockers)
    assert result.decision_label is DecisionLabel.DO_NOT_BID


def test_remediable_blocker_with_time_is_conditional() -> None:
    """An unmet mandatory item with 3+ weeks to fix is conditional, not do-not-bid."""
    result = calculate_readiness(
        strong_inputs(
            requirements=[
                req("certification", ComplianceStatus.NOT_MET.value),
                req("technical_capability", ComplianceStatus.MET.value),
            ],
            deadline_feasibility_days=30,
        )
    )
    assert result.hard_blockers
    assert result.decision_label is DecisionLabel.CONDITIONAL_BID


def test_hard_blocker_overrides_a_high_numeric_score() -> None:
    # Everything else is strong, but a passed deadline forces do_not_bid.
    result = calculate_readiness(
        strong_inputs(
            submission_deadline=datetime.now(tz=UTC) - timedelta(days=1),
            deadline_feasibility_days=-1,
        )
    )
    assert result.overall_score >= 60  # numerically it would be a bid
    assert result.decision_label is DecisionLabel.DO_NOT_BID


# --- Individual dimensions -----------------------------------------------------------------


def test_mandatory_compliance_uses_partial_fractions() -> None:
    result = calculate_readiness(
        strong_inputs(
            requirements=[
                req("staffing", ComplianceStatus.MET.value),
                req("staffing", ComplianceStatus.PARTIALLY_MET.value),
            ]
        )
    )
    dim = next(d for d in result.dimensions if d.key == "mandatory_compliance")
    assert dim.raw_score == 75.0  # (1.0 + 0.5) / 2 * 100


@pytest.mark.parametrize(
    ("days", "expected_min", "expected_max"),
    [(-1, 0, 0), (2, 0, 0), (5, 25, 25), (10, 55, 55), (18, 80, 80), (30, 100, 100)],
)
def test_deadline_bands(days: int, expected_min: int, expected_max: int) -> None:
    result = calculate_readiness(strong_inputs(deadline_feasibility_days=days))
    dim = next(d for d in result.dimensions if d.key == "deadline_feasibility")
    assert expected_min <= dim.raw_score <= expected_max


def test_contract_risk_deducts_by_severity() -> None:
    result = calculate_readiness(
        strong_inputs(
            risks=[RiskScore("critical", "termination"), RiskScore("high", "payment_terms")]
        )
    )
    dim = next(d for d in result.dimensions if d.key == "contract_risk")
    assert dim.raw_score == 55.0  # 100 - 30 - 15
