"""Deterministic evidence matching.

Pure functions over a requirement and the company's verified evidence. Deterministic rules run
first for the things that can be checked exactly — certifications by name, geography, licence
activities (`docs/03` §9). Semantic capability matching (an LLM assist) is layered on top by the
pipeline only when deterministic matching is inconclusive.

The governing rule: failing to find evidence yields `needs_clarification` or `not_met`, never a
claim that the company lacks the capability (`docs/03` §9). Only user-verified evidence counts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.enums import EvidenceCategory, MatchStatus, RequirementCategory


@dataclass(frozen=True, slots=True)
class EvidenceFact:
    """The slice of a verified evidence item that matching reads."""

    id: str
    category: str
    title: str
    tags: tuple[str, ...]
    is_verified: bool


@dataclass(frozen=True, slots=True)
class RequirementFact:
    """The slice of a requirement that matching reads."""

    category: str
    normalized_text: str
    expected_evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MatchOutcome:
    status: MatchStatus
    explanation: str
    matched_evidence_ids: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    confidence: float = 1.0
    #: True when deterministic rules were conclusive; False when the pipeline should try a
    #: semantic assist before accepting the outcome.
    deterministic: bool = True


#: Requirement categories that map to an evidence category for an exact check.
_CATEGORY_TO_EVIDENCE: dict[str, str] = {
    RequirementCategory.CERTIFICATION.value: EvidenceCategory.CERTIFICATION.value,
    RequirementCategory.INSURANCE.value: EvidenceCategory.INSURANCE.value,
    RequirementCategory.LEGAL_REGISTRATION.value: EvidenceCategory.TRADE_LICENCE.value,
    RequirementCategory.FINANCIAL.value: EvidenceCategory.FINANCIAL_STATEMENT.value,
    RequirementCategory.EXPERIENCE.value: EvidenceCategory.PREVIOUS_PROJECT.value,
}

#: Categories that are about the tender process, not company capability — nothing to match.
_NOT_APPLICABLE_CATEGORIES = {
    RequirementCategory.SUBMISSION_INSTRUCTION.value,
    RequirementCategory.DEADLINE.value,
    RequirementCategory.COMMERCIAL.value,
    RequirementCategory.CONTRACTUAL.value,
}


def _tokens(text: str) -> set[str]:
    return {t for t in text.casefold().replace("/", " ").replace("-", " ").split() if len(t) > 2}


def match_requirement(requirement: RequirementFact, evidence: list[EvidenceFact]) -> MatchOutcome:
    """Classify how well the company's verified evidence satisfies one requirement."""
    verified = [e for e in evidence if e.is_verified]

    if requirement.category in _NOT_APPLICABLE_CATEGORIES:
        return MatchOutcome(
            status=MatchStatus.NOT_APPLICABLE,
            explanation="This requirement concerns the tender process, not company capability.",
        )

    evidence_category = _CATEGORY_TO_EVIDENCE.get(requirement.category)
    if evidence_category is None:
        # No deterministic mapping (e.g. technical capability, staffing) — defer to a semantic
        # assist rather than guessing.
        return MatchOutcome(
            status=MatchStatus.NEEDS_CLARIFICATION,
            explanation="No exact evidence rule applies; requires capability review.",
            confidence=0.4,
            deterministic=False,
        )

    candidates = [e for e in verified if e.category == evidence_category]
    if not candidates:
        # Absence is a clarification/gap, never a proven lack (docs/03 §9).
        return MatchOutcome(
            status=MatchStatus.NOT_MET,
            explanation=(
                f"No verified {evidence_category.replace('_', ' ')} evidence is on file for this "
                "requirement. This reflects the current profile, not a proven absence."
            ),
            missing_evidence=list(requirement.expected_evidence)
            or [evidence_category.replace("_", " ")],
        )

    # Prefer a candidate whose title/tags overlap the requirement's key terms.
    want = _tokens(requirement.normalized_text) | {
        t for item in requirement.expected_evidence for t in _tokens(item)
    }
    for candidate in candidates:
        have = _tokens(candidate.title) | {t for tag in candidate.tags for t in _tokens(tag)}
        if want & have:
            return MatchOutcome(
                status=MatchStatus.MET,
                explanation=f"Matched verified evidence: {candidate.title}.",
                matched_evidence_ids=[candidate.id],
            )

    # Right category on file but no term overlap — partial, needs a human glance.
    return MatchOutcome(
        status=MatchStatus.PARTIALLY_MET,
        explanation=(
            f"Verified {evidence_category.replace('_', ' ')} evidence exists but does not clearly "
            "match this requirement's specifics."
        ),
        matched_evidence_ids=[candidates[0].id],
        confidence=0.6,
    )
