"""Deterministic bid-readiness scoring.

The LLM never produces the score (`docs/03` §11, CLAUDE.md). This module takes validated,
persisted findings and applies explicit weighted rules to yield a repeatable 0-100 score, a
per-dimension breakdown, hard blockers, and a decision label. Same inputs, same output, always.

Everything here is a pure function over dataclasses — no ORM, no I/O — so scoring is trivially
testable and its determinism is verifiable (`docs/07` §2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.domain.enums import (
    ComplianceStatus,
    DecisionLabel,
    RequirementObligation,
    RiskSeverity,
)

SCORING_VERSION = "1.0.0"

#: Dimension weights, summing to 100 (`docs/03` §11). Checked at import.
WEIGHTS: dict[str, int] = {
    "eligibility_fit": 25,
    "mandatory_compliance": 25,
    "capability_experience": 15,
    "evidence_completeness": 15,
    "deadline_feasibility": 10,
    "contract_risk": 10,
}

DIMENSION_LABELS = {
    "eligibility_fit": "Eligibility fit",
    "mandatory_compliance": "Mandatory compliance",
    "capability_experience": "Capability and experience",
    "evidence_completeness": "Evidence completeness",
    "deadline_feasibility": "Deadline feasibility",
    "contract_risk": "Contract risk",
}

if sum(WEIGHTS.values()) != 100:  # pragma: no cover - configuration guard
    raise RuntimeError("Scoring dimension weights must total 100")

#: Compliance → completion fraction for mandatory-compliance scoring (`docs/03` §11).
_COMPLIANCE_FRACTION = {
    ComplianceStatus.MET.value: 1.0,
    ComplianceStatus.PARTIALLY_MET.value: 0.5,
    ComplianceStatus.NEEDS_CLARIFICATION.value: 0.25,
    ComplianceStatus.NOT_MET.value: 0.0,
}

#: Contract-risk deductions from a 100 base, by severity (`docs/03` §11).
_RISK_DEDUCTION = {
    RiskSeverity.CRITICAL.value: 30,
    RiskSeverity.HIGH.value: 15,
    RiskSeverity.MEDIUM.value: 7,
    RiskSeverity.LOW.value: 2,
}


@dataclass(frozen=True, slots=True)
class RequirementScore:
    """The scoring-relevant slice of one canonical requirement (post-review status)."""

    category: str
    obligation: str
    status: str  # effective compliance status (reviewed if set, else machine)
    expected_evidence_count: int
    satisfied_evidence_count: int


@dataclass(frozen=True, slots=True)
class RiskScore:
    severity: str
    risk_type: str


@dataclass(frozen=True, slots=True)
class ScoringInput:
    requirements: list[RequirementScore]
    risks: list[RiskScore]
    submission_deadline: datetime | None
    deadline_feasibility_days: int | None  # days from now to deadline, precomputed
    bid_bond_available: bool | None


@dataclass(frozen=True, slots=True)
class DimensionScore:
    key: str
    label: str
    raw_score: float  # 0-100 before weighting
    weight: int
    weighted_score: float
    explanation: str


@dataclass(frozen=True, slots=True)
class HardBlocker:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ReadinessResult:
    overall_score: float
    decision_label: DecisionLabel
    dimensions: list[DimensionScore]
    hard_blockers: list[HardBlocker]
    assumptions: list[str] = field(default_factory=list)
    version: str = SCORING_VERSION


def _mandatory(reqs: list[RequirementScore]) -> list[RequirementScore]:
    return [r for r in reqs if r.obligation == RequirementObligation.MANDATORY.value]


def _eligibility_fit(reqs: list[RequirementScore]) -> tuple[float, str]:
    """Eligibility = mandatory legal/registration and certification requirements."""
    eligibility = [
        r
        for r in _mandatory(reqs)
        if r.category in {"legal_registration", "certification", "bid_bond_guarantee"}
    ]
    if not eligibility:
        return 100.0, "No mandatory eligibility conditions were identified."

    blockers = [r for r in eligibility if r.status == ComplianceStatus.NOT_MET.value]
    unclear = [r for r in eligibility if r.status == ComplianceStatus.NEEDS_CLARIFICATION.value]

    if len(blockers) > 1:
        return 0.0, f"{len(blockers)} mandatory eligibility conditions are unmet."
    if len(blockers) == 1:
        return 20.0, "One mandatory eligibility condition is unmet."
    if unclear:
        return 75.0, f"{len(unclear)} eligibility condition(s) require clarification."
    return 100.0, "All identified eligibility conditions are met."


def _mandatory_compliance(reqs: list[RequirementScore]) -> tuple[float, str]:
    mandatory = _mandatory(reqs)
    if not mandatory:
        return 100.0, "No mandatory requirements were identified."
    total = sum(_COMPLIANCE_FRACTION.get(r.status, 0.0) for r in mandatory)
    score = round(total / len(mandatory) * 100, 1)
    met = sum(1 for r in mandatory if r.status == ComplianceStatus.MET.value)
    return score, f"{met} of {len(mandatory)} mandatory requirements are fully met."


def _capability_experience(reqs: list[RequirementScore]) -> tuple[float, str]:
    relevant = [r for r in reqs if r.category in {"technical_capability", "experience", "staffing"}]
    if not relevant:
        return 100.0, "No specific capability or experience requirements were identified."
    total = sum(_COMPLIANCE_FRACTION.get(r.status, 0.0) for r in relevant)
    score = round(total / len(relevant) * 100, 1)
    return score, f"Capability and experience requirements are {score:.0f}% satisfied."


def _evidence_completeness(reqs: list[RequirementScore]) -> tuple[float, str]:
    expected = sum(r.expected_evidence_count for r in reqs)
    if expected == 0:
        return 100.0, "No specific evidence items were expected."
    satisfied = sum(min(r.satisfied_evidence_count, r.expected_evidence_count) for r in reqs)
    score = round(satisfied / expected * 100, 1)
    return score, f"{satisfied} of {expected} expected evidence items are on file."


def _deadline_feasibility(days: int | None) -> tuple[float, str]:
    if days is None:
        return 50.0, "No submission deadline was found; assuming moderate time pressure."
    if days < 0:
        return 0.0, "The submission deadline has already passed."
    if days < 3:
        return 0.0, f"Only {days} day(s) remain before the deadline."
    if days <= 6:
        return 25.0, f"{days} days remain — very tight."
    if days <= 13:
        return 55.0, f"{days} days remain — tight."
    if days <= 21:
        return 80.0, f"{days} days remain — workable."
    return 100.0, f"{days} days remain — comfortable."


def _contract_risk(risks: list[RiskScore]) -> tuple[float, str]:
    score = 100.0
    # Cap duplicate deductions for the same risk family (`docs/03` §11).
    seen_types: set[str] = set()
    for risk in risks:
        if risk.risk_type in seen_types and risk.severity in {
            RiskSeverity.LOW.value,
            RiskSeverity.MEDIUM.value,
        }:
            continue
        seen_types.add(risk.risk_type)
        score -= _RISK_DEDUCTION.get(risk.severity, 0)
    score = max(score, 0.0)
    critical = sum(1 for r in risks if r.severity == RiskSeverity.CRITICAL.value)
    return score, f"{len(risks)} risk(s) identified, {critical} critical."


def _hard_blockers(data: ScoringInput) -> list[HardBlocker]:
    """Conditions that override the numeric label (`docs/03` §12)."""
    blockers: list[HardBlocker] = []

    if data.deadline_feasibility_days is not None and data.deadline_feasibility_days < 0:
        blockers.append(HardBlocker("deadline_passed", "The submission deadline has passed."))

    for req in _mandatory(data.requirements):
        if (
            req.category in {"legal_registration", "certification"}
            and req.status == ComplianceStatus.NOT_MET.value
        ):
            blockers.append(
                HardBlocker(
                    "mandatory_eligibility_unmet",
                    f"A mandatory {req.category.replace('_', ' ')} requirement is unmet.",
                )
            )
            break

    if data.bid_bond_available is False and any(
        r.category == "bid_bond_guarantee" and r.obligation == RequirementObligation.MANDATORY.value
        for r in data.requirements
    ):
        blockers.append(
            HardBlocker(
                "bid_bond_unavailable",
                "A bid bond is required but marked unavailable.",
            )
        )

    return blockers


def _label_from_score(score: float) -> DecisionLabel:
    if score >= 80:
        return DecisionLabel.STRONG_BID
    if score >= 60:
        return DecisionLabel.CONDITIONAL_BID
    if score >= 40:
        return DecisionLabel.WEAK_BID
    return DecisionLabel.DO_NOT_BID


def calculate_readiness(data: ScoringInput) -> ReadinessResult:
    """Score a tender's readiness deterministically from validated findings."""
    raw = {
        "eligibility_fit": _eligibility_fit(data.requirements),
        "mandatory_compliance": _mandatory_compliance(data.requirements),
        "capability_experience": _capability_experience(data.requirements),
        "evidence_completeness": _evidence_completeness(data.requirements),
        "deadline_feasibility": _deadline_feasibility(data.deadline_feasibility_days),
        "contract_risk": _contract_risk(data.risks),
    }

    dimensions: list[DimensionScore] = []
    overall = 0.0
    for key, (raw_score, explanation) in raw.items():
        weight = WEIGHTS[key]
        weighted = round(raw_score * weight / 100, 2)
        overall += weighted
        dimensions.append(
            DimensionScore(
                key=key,
                label=DIMENSION_LABELS[key],
                raw_score=raw_score,
                weight=weight,
                weighted_score=weighted,
                explanation=explanation,
            )
        )
    overall = round(overall, 1)

    blockers = _hard_blockers(data)

    # Hard blockers take precedence over the numeric band (`docs/03` §12-13).
    if not data.requirements:
        label = DecisionLabel.INSUFFICIENT_INFORMATION
    elif blockers:
        # Remediable-before-deadline → conditional; otherwise do-not-bid. A passed deadline is
        # never remediable.
        deadline_passed = any(b.code == "deadline_passed" for b in blockers)
        remediable = (
            not deadline_passed
            and data.deadline_feasibility_days is not None
            and data.deadline_feasibility_days >= 14
        )
        label = DecisionLabel.CONDITIONAL_BID if remediable else DecisionLabel.DO_NOT_BID
    else:
        label = _label_from_score(overall)

    assumptions = [
        "Only evidence marked verified by the user was used.",
        "Requirements without a verified citation were excluded from scoring.",
        f"Score calculated deterministically by scoring version {SCORING_VERSION}.",
    ]

    return ReadinessResult(
        overall_score=overall,
        decision_label=label,
        dimensions=dimensions,
        hard_blockers=blockers,
        assumptions=assumptions,
    )


def days_until(deadline: datetime | None, *, now: datetime | None = None) -> int | None:
    if deadline is None:
        return None
    reference = now or datetime.now(tz=UTC)
    return (deadline - reference).days
