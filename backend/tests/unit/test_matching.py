"""Deterministic evidence matching rules."""

from __future__ import annotations

import pytest

from app.domain.enums import MatchStatus
from app.domain.matching import EvidenceFact, RequirementFact, match_requirement


def evidence(category: str, title: str, *, verified: bool = True, tags: tuple[str, ...] = ()):
    return EvidenceFact(id="e1", category=category, title=title, tags=tags, is_verified=verified)


def requirement(category: str, text: str = "requirement text", evidence_items=()):
    return RequirementFact(
        category=category, normalized_text=text, expected_evidence=tuple(evidence_items)
    )


def test_matching_certification_by_title_overlap_is_met() -> None:
    outcome = match_requirement(
        requirement("certification", "Hold a valid ISO 9001 certificate"),
        [evidence("certification", "ISO 9001 Quality Certificate", tags=("iso",))],
    )
    assert outcome.status is MatchStatus.MET
    assert outcome.matched_evidence_ids == ["e1"]


def test_missing_evidence_is_not_met_not_proof_of_absence() -> None:
    outcome = match_requirement(requirement("certification", "ISO 14001 required"), [])
    assert outcome.status is MatchStatus.NOT_MET
    # The explanation must frame it as current-profile, not proven absence (docs/03 §9).
    assert "not a proven absence" in outcome.explanation.lower()


def test_unverified_evidence_does_not_count() -> None:
    outcome = match_requirement(
        requirement("certification", "ISO 9001"),
        [evidence("certification", "ISO 9001", verified=False)],
    )
    assert outcome.status is MatchStatus.NOT_MET


def test_right_category_no_overlap_is_partial() -> None:
    outcome = match_requirement(
        requirement("certification", "Hold OHSAS 18001 safety certification"),
        [evidence("certification", "ISO 9001 Quality Certificate")],
    )
    assert outcome.status is MatchStatus.PARTIALLY_MET
    assert outcome.confidence < 1.0


def test_process_requirements_are_not_applicable() -> None:
    for category in ("submission_instruction", "deadline", "commercial"):
        outcome = match_requirement(requirement(category), [])
        assert outcome.status is MatchStatus.NOT_APPLICABLE


def test_uncmapped_category_defers_to_semantic_review() -> None:
    outcome = match_requirement(requirement("technical_capability"), [])
    assert outcome.status is MatchStatus.NEEDS_CLARIFICATION
    assert outcome.deterministic is False


@pytest.mark.parametrize(
    ("req_cat", "ev_cat"),
    [
        ("legal_registration", "trade_licence"),
        ("insurance", "insurance"),
        ("financial", "financial_statement"),
    ],
)
def test_category_mapping(req_cat: str, ev_cat: str) -> None:
    outcome = match_requirement(
        requirement(req_cat, "a matching keyword phrase here"),
        [evidence(ev_cat, "a matching keyword phrase document")],
    )
    assert outcome.status is MatchStatus.MET
