"""Deterministic screening scoring: credit per verdict, band renormalisation, and honesty.

The buyer ranks applicants on this number and the vendor is told what to fix because of it, so
the tests below pin the arithmetic *and* the wording: an empty checklist must not score 0, and
an unmatched document must never be reported as one the vendor does not have.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from app.domain.enums import DocumentScreeningVerdict, RequiredDocumentType
from app.domain.screening import (
    DOCUMENT_TYPE_LABELS,
    MANDATORY_BAND_WEIGHT,
    MET_VERDICTS,
    OPTIONAL_BAND_WEIGHT,
    SCREENING_SCORING_VERSION,
    VERDICT_CREDIT,
    RequirementVerdict,
    ScreeningRequirement,
    calculate_screening_score,
)

PRESENT = DocumentScreeningVerdict.PRESENT
EXPIRED = DocumentScreeningVerdict.PRESENT_EXPIRED
UNREADABLE = DocumentScreeningVerdict.PRESENT_UNREADABLE
MISSING = DocumentScreeningVerdict.MISSING
NOT_APPLICABLE = DocumentScreeningVerdict.NOT_APPLICABLE

#: Distinct types, because a screening holds at most one finding per document type.
TYPES = list(RequiredDocumentType)


def entry(
    verdict: DocumentScreeningVerdict,
    *,
    mandatory: bool = True,
    weight: int = 1,
    document_type: RequiredDocumentType = RequiredDocumentType.TRADE_LICENCE,
) -> RequirementVerdict:
    return RequirementVerdict(
        requirement=ScreeningRequirement(
            document_type=document_type, is_mandatory=mandatory, weight=weight
        ),
        verdict=verdict,
    )


def checklist(*verdicts: RequirementVerdict) -> list[RequirementVerdict]:
    """Re-key each entry onto a distinct document type so uniqueness holds."""
    return [
        RequirementVerdict(
            requirement=ScreeningRequirement(
                document_type=TYPES[position],
                is_mandatory=item.requirement.is_mandatory,
                weight=item.requirement.weight,
            ),
            verdict=item.verdict,
        )
        for position, item in enumerate(verdicts)
    ]


# --- Structural guarantees -----------------------------------------------------------------


def test_band_weights_total_one() -> None:
    # The 0-100 bound is arithmetic, not clamping. If this drifts the module raises on import.
    mandatory, optional = MANDATORY_BAND_WEIGHT, OPTIONAL_BAND_WEIGHT
    assert mandatory + optional == 1
    assert (mandatory, optional) == (Fraction(4, 5), Fraction(1, 5))


def test_every_verdict_has_a_credit_and_every_document_type_a_label() -> None:
    assert set(VERDICT_CREDIT) == set(DocumentScreeningVerdict)
    assert set(DOCUMENT_TYPE_LABELS) == set(RequiredDocumentType)
    assert all(label.strip() for label in DOCUMENT_TYPE_LABELS.values())


def test_met_verdicts_are_exactly_the_ones_earning_credit() -> None:
    """A count of "met" that disagreed with the score beside it would be indefensible."""
    earning = {v for v, credit in VERDICT_CREDIT.items() if credit is not None and credit > 0}
    assert MET_VERDICTS == earning == {PRESENT, EXPIRED}


def test_weight_outside_the_permitted_range_is_rejected() -> None:
    # Mirrors the database check constraint; a zero-weight band would divide by zero.
    for weight in (0, -1, 11):
        with pytest.raises(ValueError, match="weight must be between"):
            ScreeningRequirement(
                document_type=RequiredDocumentType.TRADE_LICENCE,
                is_mandatory=True,
                weight=weight,
            )


# --- Credit per verdict --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("verdict", "expected_score", "expected_credit"),
    [
        (PRESENT, 100, 1.0),
        (EXPIRED, 50, 0.5),
        (UNREADABLE, 0, 0.0),
        (MISSING, 0, 0.0),
    ],
)
def test_single_mandatory_requirement_scores_its_credit(
    verdict: DocumentScreeningVerdict, expected_score: int, expected_credit: float
) -> None:
    result = calculate_screening_score([entry(verdict, weight=7)])
    assert result.score == expected_score
    assert result.findings[0].credit_ratio == expected_credit
    assert result.version == SCREENING_SCORING_VERSION


def test_expired_earns_half_its_weight_not_half_the_requirements() -> None:
    """Credit is weighted: an expired heavy item outscores a present light one."""
    heavy_expired = calculate_screening_score(
        checklist(entry(EXPIRED, weight=10), entry(MISSING, weight=1))
    )
    light_present = calculate_screening_score(
        checklist(entry(MISSING, weight=10), entry(PRESENT, weight=1))
    )
    assert heavy_expired.score == 45  # 5 of 11
    assert light_present.score == 9  # 1 of 11


def test_unreadable_and_missing_both_score_zero_but_are_reported_apart() -> None:
    result = calculate_screening_score(
        checklist(entry(UNREADABLE, weight=3), entry(MISSING, weight=2))
    )
    assert result.score == 0
    assert [f.verdict for f in result.missing] == [MISSING]
    assert [f.verdict for f in result.unreadable] == [UNREADABLE]
    # The two need different actions from the vendor, so they must never be merged.
    assert not set(result.missing) & set(result.unreadable)


def test_unreadable_counts_as_neither_met_nor_excluded() -> None:
    result = calculate_screening_score([entry(UNREADABLE, weight=4)])
    assert (result.mandatory_met, result.mandatory_total) == (0, 1)
    assert result.has_blocking_gap is True


# --- Band blending and renormalisation -------------------------------------------------------


def test_both_bands_blend_eighty_twenty() -> None:
    result = calculate_screening_score(
        checklist(
            entry(PRESENT, mandatory=True, weight=1),
            entry(MISSING, mandatory=False, weight=1),
        )
    )
    # 0.8 * 1 + 0.2 * 0
    assert result.score == 80
    assert result.mandatory_ratio == 1.0
    assert result.optional_ratio == 0.0


def test_no_optional_requirements_renormalises_mandatory_to_one() -> None:
    """Half the mandatory weight met must score 50, not 40 — the optional term is dropped."""
    result = calculate_screening_score(
        checklist(entry(PRESENT, weight=5), entry(MISSING, weight=5))
    )
    assert result.score == 50
    assert result.optional_ratio is None
    assert result.optional_total == 0


def test_no_mandatory_requirements_scores_on_optional_alone() -> None:
    result = calculate_screening_score(
        checklist(
            entry(PRESENT, mandatory=False, weight=5),
            entry(MISSING, mandatory=False, weight=5),
        )
    )
    assert result.score == 50
    assert result.mandatory_ratio is None
    assert result.mandatory_total == 0
    # Nothing mandatory was asked for, so nothing mandatory can be blocking.
    assert result.has_blocking_gap is False


def test_optional_band_cannot_outweigh_a_mandatory_gap() -> None:
    """A perfect set of nice-to-haves is worth at most 20 while the licence is unmatched."""
    result = calculate_screening_score(
        checklist(
            entry(MISSING, mandatory=True, weight=10),
            entry(PRESENT, mandatory=False, weight=10),
            entry(PRESENT, mandatory=False, weight=10),
        )
    )
    assert result.score == 20
    assert result.has_blocking_gap is True


# --- Nothing to assess -----------------------------------------------------------------------


def test_empty_checklist_scores_none_not_zero() -> None:
    """0 would read as "supplied nothing" about a vendor who was asked for nothing."""
    result = calculate_screening_score([])
    assert result.score is None
    assert result.mandatory_ratio is None
    assert result.optional_ratio is None
    assert result.findings == ()
    assert result.missing == ()
    assert result.unreadable == ()
    assert result.has_blocking_gap is False
    assert (result.mandatory_total, result.optional_total) == (0, 0)


def test_a_checklist_of_only_not_applicable_also_scores_none() -> None:
    result = calculate_screening_score(
        checklist(
            entry(NOT_APPLICABLE, mandatory=True, weight=8),
            entry(NOT_APPLICABLE, mandatory=False, weight=3),
        )
    )
    assert result.score is None
    assert (result.mandatory_total, result.optional_total) == (0, 0)
    assert result.has_blocking_gap is False
    # The requirements are still reported — the buyer sees they were withdrawn, not hidden.
    assert len(result.findings) == 2


# --- not_applicable exclusion ----------------------------------------------------------------


def test_not_applicable_leaves_both_numerator_and_denominator() -> None:
    """It neither credits the vendor nor penalises them: the row simply is not scored."""
    without = calculate_screening_score([entry(PRESENT, weight=5)])
    with_excluded = calculate_screening_score(
        checklist(entry(PRESENT, weight=5), entry(NOT_APPLICABLE, weight=5))
    )
    assert with_excluded.score == without.score == 100
    assert with_excluded.mandatory_total == 1
    assert with_excluded.mandatory_met == 1


def test_not_applicable_is_not_a_blocking_gap() -> None:
    result = calculate_screening_score(
        checklist(entry(PRESENT, weight=1), entry(NOT_APPLICABLE, weight=10))
    )
    assert result.has_blocking_gap is False
    assert result.score == 100


def test_not_applicable_optional_band_falls_back_to_mandatory_alone() -> None:
    """Excluding the last optional row must renormalise, not blend against an empty band."""
    result = calculate_screening_score(
        checklist(
            entry(PRESENT, mandatory=True, weight=1),
            entry(MISSING, mandatory=True, weight=1),
            entry(NOT_APPLICABLE, mandatory=False, weight=9),
        )
    )
    assert result.optional_ratio is None
    assert result.score == 50


def test_not_applicable_findings_are_excluded_from_the_ratio_but_keep_their_credit_none() -> None:
    result = calculate_screening_score([entry(NOT_APPLICABLE, weight=6)])
    finding = result.findings[0]
    assert finding.credit is None
    assert finding.credit_ratio is None
    assert finding.counted is False
    assert finding.met is False


# --- Counts ---------------------------------------------------------------------------------


def test_counts_treat_expired_as_supplied() -> None:
    """A partially credited item is still an item the vendor uploaded."""
    result = calculate_screening_score(
        checklist(
            entry(PRESENT, mandatory=True, weight=1),
            entry(EXPIRED, mandatory=True, weight=1),
            entry(MISSING, mandatory=True, weight=1),
            entry(EXPIRED, mandatory=False, weight=1),
            entry(UNREADABLE, mandatory=False, weight=1),
        )
    )
    assert (result.mandatory_met, result.mandatory_total) == (2, 3)
    assert (result.optional_met, result.optional_total) == (1, 2)


def test_expired_mandatory_document_is_not_a_blocking_gap() -> None:
    # A renewal is a different conversation from an absent document.
    result = calculate_screening_score([entry(EXPIRED, weight=4)])
    assert result.has_blocking_gap is False
    assert result.score == 50


def test_blocking_gap_is_set_by_any_unmet_mandatory_requirement() -> None:
    result = calculate_screening_score(
        checklist(
            entry(PRESENT, mandatory=True, weight=9),
            entry(PRESENT, mandatory=True, weight=9),
            entry(MISSING, mandatory=True, weight=1),
        )
    )
    assert result.has_blocking_gap is True
    # The score is still published: the buyer decides whether one gap sinks a strong bid.
    assert result.score == 95


def test_counts_agree_with_the_stored_orm_definition_of_a_blocking_gap() -> None:
    """`ApplicationScreening.has_blocking_gap` recomputes this from the two stored counts."""
    for verdict in DocumentScreeningVerdict:
        result = calculate_screening_score([entry(verdict)])
        assert result.has_blocking_gap == (result.mandatory_met < result.mandatory_total)


# --- Ordering -------------------------------------------------------------------------------


def test_missing_is_ordered_mandatory_first_then_heaviest() -> None:
    result = calculate_screening_score(
        checklist(
            entry(MISSING, mandatory=False, weight=10),
            entry(MISSING, mandatory=True, weight=2),
            entry(MISSING, mandatory=True, weight=9),
            entry(MISSING, mandatory=False, weight=1),
        )
    )
    assert [(f.is_mandatory, f.weight) for f in result.missing] == [
        (True, 9),
        (True, 2),
        (False, 10),
        (False, 1),
    ]


def test_unreadable_uses_the_same_ordering() -> None:
    result = calculate_screening_score(
        checklist(
            entry(UNREADABLE, mandatory=False, weight=8),
            entry(UNREADABLE, mandatory=True, weight=3),
        )
    )
    assert [f.is_mandatory for f in result.unreadable] == [True, False]


def test_findings_keep_the_checklist_order_they_were_supplied_in() -> None:
    entries = checklist(
        entry(MISSING, weight=1),
        entry(PRESENT, weight=10),
        entry(EXPIRED, weight=5),
    )
    result = calculate_screening_score(entries)
    assert [f.document_type for f in result.findings] == [
        item.requirement.document_type for item in entries
    ]


def test_equal_weights_break_ties_deterministically() -> None:
    entries = checklist(*(entry(MISSING, weight=4) for _ in range(4)))
    first = [f.document_type for f in calculate_screening_score(entries).missing]
    shuffled = list(reversed(entries))
    second = [f.document_type for f in calculate_screening_score(shuffled).missing]
    assert first == second


# --- Rounding and bounds ---------------------------------------------------------------------


def test_score_is_rounded_to_a_whole_number_within_bounds() -> None:
    result = calculate_screening_score(
        checklist(entry(PRESENT, weight=1), entry(MISSING, weight=2))
    )
    assert result.score == 33  # 1/3 → 33.33…


@pytest.mark.parametrize(
    ("present_weight", "missing_weight", "expected"),
    [
        (1, 7, 12),  # 12.5 → ties resolve to even
        (3, 5, 38),  # 37.5 → ties resolve to even
        (1, 1, 50),
        (7, 1, 88),  # 87.5 → ties resolve to even
    ],
)
def test_half_point_boundaries_round_deterministically(
    present_weight: int, missing_weight: int, expected: int
) -> None:
    """Exact rational arithmetic, one rounding step, ties to even — never float drift."""
    result = calculate_screening_score(
        checklist(entry(PRESENT, weight=present_weight), entry(MISSING, weight=missing_weight))
    )
    assert result.score == expected


def test_score_never_leaves_the_zero_to_one_hundred_range() -> None:
    for verdicts in (
        [entry(PRESENT, weight=10)],
        [entry(MISSING, weight=10)],
        checklist(
            entry(EXPIRED, mandatory=True, weight=10),
            entry(EXPIRED, mandatory=False, weight=10),
        ),
    ):
        score = calculate_screening_score(verdicts).score
        assert score is not None
        assert 0 <= score <= 100


def test_same_input_always_produces_the_same_score() -> None:
    entries = checklist(
        entry(PRESENT, mandatory=True, weight=7),
        entry(EXPIRED, mandatory=True, weight=3),
        entry(MISSING, mandatory=False, weight=9),
        entry(NOT_APPLICABLE, mandatory=False, weight=2),
    )
    scores = {calculate_screening_score(entries).score for _ in range(10)}
    assert scores == {round(100 * (Fraction(4, 5) * Fraction(17, 20) + Fraction(1, 5) * 0))}


# --- Explainability --------------------------------------------------------------------------


def test_missing_wording_does_not_assert_the_vendor_lacks_the_document() -> None:
    """`CLAUDE.md`: "not found" is not proof of non-existence (`docs/09` §10.6)."""
    result = calculate_screening_score(
        [entry(MISSING, document_type=RequiredDocumentType.TRADE_LICENCE)]
    )
    explanation = result.missing[0].explanation.lower()
    assert "documents supplied" in explanation
    assert "not proof" in explanation
    for forbidden in ("does not have", "has no ", "lacks", "the vendor is missing"):
        assert forbidden not in explanation


def test_unreadable_wording_asks_for_a_re_upload_rather_than_the_document() -> None:
    result = calculate_screening_score([entry(UNREADABLE)])
    explanation = result.unreadable[0].explanation.lower()
    assert "could not be read" in explanation
    assert "missing" not in explanation


def test_expired_wording_frames_it_as_a_renewal() -> None:
    result = calculate_screening_score([entry(EXPIRED)])
    assert "renewal" in result.findings[0].explanation.lower()


def test_every_finding_carries_a_label_and_an_explanation_naming_it() -> None:
    entries = checklist(
        entry(PRESENT),
        entry(EXPIRED),
        entry(UNREADABLE),
        entry(MISSING),
        entry(NOT_APPLICABLE),
    )
    result = calculate_screening_score(entries)
    assert len(result.findings) == len(entries)
    for finding in result.findings:
        assert finding.label == DOCUMENT_TYPE_LABELS[finding.document_type]
        assert finding.label in finding.explanation
        assert finding.explanation.endswith(".")
