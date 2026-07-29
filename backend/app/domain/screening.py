"""Deterministic screening score for an application's document checklist.

The classifier proposes which upload satisfies which requirement and the verifier throws away
every proposal whose quote does not re-match the stored page text (`docs/09` §4). What is left
is a list of verdicts. This module turns that list into a number. The model never sees this
arithmetic and never produces the score (`CLAUDE.md`, `docs/09` §10.5).

Pure functions over frozen dataclasses — no ORM, no I/O, no clock — the same shape as
`app/domain/completion.py`, so the whole scoring rule is testable without a database.

**Why the bands are 80/20.** A buyer's checklist has two kinds of entries. Mandatory ones decide
whether a bid can be considered at all; optional ones separate a good submission from a complete
one. Splitting the score 0.8/0.2 keeps the optional band meaningful without ever letting a pile
of nice-to-haves outweigh a missing trade licence.

**Why arithmetic is exact.** Ratios are :class:`~fractions.Fraction`, not `float`. A vendor's
score is stored, ranked, and shown to a buyer; a binary rounding error deciding 79 vs 80 at the
boundary is not a defect anyone would ever find. Integer weights in, exact rational out, one
rounding step at the very end.

**Why `not_applicable` leaves both sides of the ratio.** Treating it as unearned weight would
penalise a vendor for a requirement the buyer withdrew; treating it as earned would credit them
for work they never did. Removing it entirely is the only honest option, and it is why
`mandatory_total` here is a count of *assessed* requirements rather than of checklist rows.

**Why an empty checklist scores `None` rather than 0.** A buyer who asked for no documents has
told us nothing about this vendor. Publishing 0 would read as "supplied nothing" — a libel on a
vendor who was asked for nothing. Callers must render the absence, not the number.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from fractions import Fraction

from app.domain.enums import DocumentScreeningVerdict, RequiredDocumentType

#: Bump when the credit table, the band split, or the rounding changes. Stored on the screening
#: row so a score produced by an older rule stays identifiable after the rule moves on.
SCREENING_SCORING_VERSION = "1.0.0"

#: Mirrors the `weight BETWEEN 1 AND 10` check constraint on `listing_document_requirements`.
#: The lower bound is load-bearing here: a zero-weight band would divide by zero.
MIN_REQUIREMENT_WEIGHT = 1
MAX_REQUIREMENT_WEIGHT = 10

#: Band split from `docs/09` §8: `score = round(100 * (0.8 * mandatory + 0.2 * optional))`.
#: Exact fifths rather than 0.8/0.2 floats so the blend introduces no representation error.
MANDATORY_BAND_WEIGHT = Fraction(4, 5)
OPTIONAL_BAND_WEIGHT = Fraction(1, 5)

#: Fraction of a requirement's weight each verdict earns. `None` means the requirement is
#: excluded from the ratio entirely — numerator *and* denominator.
#:
#: `present_expired` earns half because the document exists: that is a renewal problem, not a
#: gap. `present_unreadable` earns nothing but is reported separately from `missing`, because
#: "re-upload a readable scan" and "supply this document" are different instructions.
#:
#: `present_unverified` earns nothing either, and that is the point of it. A certificate whose
#: number is absent from the issuing register is exactly as much assurance as no certificate —
#: crediting it would mean any vendor could raise their score by typing a number onto a page.
#: It stays a separate verdict rather than collapsing into `missing` so the vendor is told the
#: real problem, which is the number rather than the file.
VERDICT_CREDIT: dict[DocumentScreeningVerdict, Fraction | None] = {
    DocumentScreeningVerdict.PRESENT: Fraction(1),
    DocumentScreeningVerdict.PRESENT_EXPIRED: Fraction(1, 2),
    DocumentScreeningVerdict.PRESENT_UNREADABLE: Fraction(0),
    DocumentScreeningVerdict.PRESENT_UNVERIFIED: Fraction(0),
    DocumentScreeningVerdict.MISSING: Fraction(0),
    DocumentScreeningVerdict.NOT_APPLICABLE: None,
}

#: Verdicts that count towards `mandatory_met` / `optional_met`. A partially credited item is
#: still an item the vendor supplied, so an expired document counts as met even though it only
#: earns half its weight.
MET_VERDICTS = frozenset(
    {DocumentScreeningVerdict.PRESENT, DocumentScreeningVerdict.PRESENT_EXPIRED}
)

#: Human wording for each checklist entry. A controlled table rather than
#: `value.replace("_", " ")`, because that renders "vat tax certificate" and "staff cvs" into
#: vendor-facing prose. Every explanation this module produces reads a label from here.
DOCUMENT_TYPE_LABELS: dict[RequiredDocumentType, str] = {
    RequiredDocumentType.TRADE_LICENCE: "trade licence",
    RequiredDocumentType.COMMERCIAL_REGISTRATION: "commercial registration",
    RequiredDocumentType.VAT_TAX_CERTIFICATE: "VAT or tax certificate",
    RequiredDocumentType.ESTABLISHMENT_CARD: "establishment card",
    RequiredDocumentType.AUTHORISED_SIGNATORY: "authorised signatory letter",
    RequiredDocumentType.COMPANY_PROFILE: "company profile",
    RequiredDocumentType.AUDITED_FINANCIALS: "audited financial statements",
    RequiredDocumentType.BANK_REFERENCE_LETTER: "bank reference letter",
    RequiredDocumentType.BID_BOND: "bid bond",
    RequiredDocumentType.PERFORMANCE_GUARANTEE: "performance guarantee",
    RequiredDocumentType.INSURANCE_CERTIFICATE: "insurance certificate",
    RequiredDocumentType.ISO_CERTIFICATION: "ISO certification",
    RequiredDocumentType.HSE_PLAN: "HSE plan",
    RequiredDocumentType.QUALITY_PLAN: "quality plan",
    RequiredDocumentType.TECHNICAL_PROPOSAL: "technical proposal",
    RequiredDocumentType.COMMERCIAL_PROPOSAL: "commercial proposal",
    RequiredDocumentType.METHOD_STATEMENT: "method statement",
    RequiredDocumentType.PROJECT_SCHEDULE: "project schedule",
    RequiredDocumentType.STAFF_CVS: "staff CVs",
    RequiredDocumentType.ORGANISATION_CHART: "organisation chart",
    RequiredDocumentType.EQUIPMENT_LIST: "equipment list",
    RequiredDocumentType.PAST_PROJECT_REFERENCES: "past project references",
    RequiredDocumentType.CLIENT_TESTIMONIAL: "client testimonial",
    RequiredDocumentType.OTHER: "supporting document",
}

# --- Import-time guards --------------------------------------------------------------------
#
# Each raises rather than asserts, so `python -O` cannot strip the check and let a mis-edited
# table produce silently wrong scores. Following `app/domain/completion.py`.

if MANDATORY_BAND_WEIGHT + OPTIONAL_BAND_WEIGHT != 1:  # pragma: no cover - configuration guard
    raise RuntimeError(
        "Screening band weights must total exactly 1, got "
        f"{MANDATORY_BAND_WEIGHT} + {OPTIONAL_BAND_WEIGHT}. The 0-100 bound is arithmetic, "
        "not clamping."
    )

if set(DocumentScreeningVerdict) != set(VERDICT_CREDIT):  # pragma: no cover - config guard
    raise RuntimeError(
        "VERDICT_CREDIT must give every DocumentScreeningVerdict a credit; missing "
        f"{sorted(set(DocumentScreeningVerdict) - set(VERDICT_CREDIT))}. A verdict with no "
        "entry would be silently unscoreable."
    )

if any(
    credit is not None and not (0 <= credit <= 1) for credit in VERDICT_CREDIT.values()
):  # pragma: no cover - configuration guard
    raise RuntimeError("Every verdict credit must lie between 0 and 1 inclusive.")

_CREDIT_EARNING_VERDICTS = {
    verdict for verdict, credit in VERDICT_CREDIT.items() if credit is not None and credit > 0
}

if MET_VERDICTS != _CREDIT_EARNING_VERDICTS:  # pragma: no cover - configuration guard
    raise RuntimeError(
        "MET_VERDICTS must be exactly the verdicts earning credit. Otherwise the counts shown "
        "to the buyer would disagree with the score they sit beside."
    )

if set(RequiredDocumentType) != set(DOCUMENT_TYPE_LABELS):  # pragma: no cover - config guard
    raise RuntimeError(
        "DOCUMENT_TYPE_LABELS must cover every RequiredDocumentType; missing "
        f"{sorted(set(RequiredDocumentType) - set(DOCUMENT_TYPE_LABELS))}."
    )


@dataclass(frozen=True, slots=True)
class ScreeningRequirement:
    """One checklist entry, as it stood when the submission was screened.

    A copy of `ListingDocumentRequirement`'s scoring-relevant fields rather than the row itself:
    a later edit to the checklist must not retroactively change what a completed screening was
    measured against.
    """

    document_type: RequiredDocumentType
    is_mandatory: bool
    #: Relative importance within its band, 1-10.
    weight: int

    def __post_init__(self) -> None:
        # Rejected here as well as in the database, because this module is reachable from tests
        # and workers that never round-trip through the check constraint, and a weight of 0
        # across a whole band would divide by zero rather than fail visibly.
        if not MIN_REQUIREMENT_WEIGHT <= self.weight <= MAX_REQUIREMENT_WEIGHT:
            raise ValueError(
                f"Requirement weight must be between {MIN_REQUIREMENT_WEIGHT} and "
                f"{MAX_REQUIREMENT_WEIGHT}, got {self.weight}."
            )


@dataclass(frozen=True, slots=True)
class RequirementVerdict:
    """A checklist entry paired with what screening concluded about it."""

    requirement: ScreeningRequirement
    verdict: DocumentScreeningVerdict


@dataclass(frozen=True, slots=True)
class RequirementFinding:
    """One scored requirement, with the reasoning that produced its contribution."""

    document_type: RequiredDocumentType
    label: str
    is_mandatory: bool
    weight: int
    verdict: DocumentScreeningVerdict
    #: Fraction of `weight` earned, or `None` when the requirement was excluded from the ratio.
    credit: Fraction | None
    met: bool
    explanation: str

    @property
    def counted(self) -> bool:
        """Whether this requirement reached the ratio at all (`not_applicable` does not)."""
        return self.credit is not None

    @property
    def credit_ratio(self) -> float | None:
        """`credit` as a float, for schemas and logs. The exact `Fraction` stays authoritative."""
        return None if self.credit is None else float(self.credit)


@dataclass(frozen=True, slots=True)
class ScreeningResult:
    """The complete deterministic outcome for one application."""

    #: 0-100, or `None` when the checklist held nothing to assess. Never conflate the two.
    score: int | None
    mandatory_met: int
    mandatory_total: int
    optional_met: int
    optional_total: int
    #: The two band ratios before blending, for display and for debugging a surprising score.
    mandatory_ratio: float | None
    optional_ratio: float | None
    #: Every requirement, in the order supplied — i.e. the buyer's checklist order.
    findings: tuple[RequirementFinding, ...]
    #: Nothing matched. Heaviest first, mandatory before optional: the vendor's to-do list.
    missing: tuple[RequirementFinding, ...]
    #: Supplied but unreadable. Deliberately not merged into `missing` — the vendor's next
    #: action is "upload a readable copy", not "find the document".
    unreadable: tuple[RequirementFinding, ...]
    #: True when an assessed mandatory requirement was not met. The score is still published:
    #: a buyer is entitled to see that an otherwise strong bid is missing one certificate
    #: (`docs/09` §8).
    has_blocking_gap: bool
    version: str = SCREENING_SCORING_VERSION


def _explain(document_type: RequiredDocumentType, verdict: DocumentScreeningVerdict) -> str:
    """Vendor- and buyer-facing wording for one verdict.

    The `missing` wording is constrained by `CLAUDE.md` and `docs/09` §10.6: it must say what
    was searched, never assert that the vendor lacks the document. The same framing as
    `app/domain/matching.py` — the documents supplied are the evidence, and their silence is
    not proof of absence.
    """
    label = DOCUMENT_TYPE_LABELS[document_type]
    match verdict:
        case DocumentScreeningVerdict.PRESENT:
            return f"The {label} requirement was matched in the documents supplied."
        case DocumentScreeningVerdict.PRESENT_EXPIRED:
            return (
                f"The {label} requirement was matched, but the document has expired. It earns "
                "half its weight: this is a renewal, not a gap."
            )
        case DocumentScreeningVerdict.PRESENT_UNREADABLE:
            return (
                f"A document was supplied for the {label} requirement, but its text could not "
                "be read and it could not be assessed. Uploading a text-based PDF or a clearer "
                "scan would allow it to be scored."
            )
        case DocumentScreeningVerdict.PRESENT_UNVERIFIED:
            return (
                f"A document was supplied for the {label} requirement, but the credential it "
                "asserts could not be confirmed against the issuing register, so it earns no "
                "credit. The finding's note records which number was checked."
            )
        case DocumentScreeningVerdict.MISSING:
            return (
                f"Nothing in the documents supplied with this application matched the {label} "
                "requirement. This reflects what was supplied, not proof that the applicant "
                "does not hold it."
            )
        case DocumentScreeningVerdict.NOT_APPLICABLE:
            return (
                f"The {label} requirement does not apply to this application and is excluded "
                "from the score."
            )

    raise ValueError(f"Unhandled screening verdict: {verdict}")


def _finding(entry: RequirementVerdict) -> RequirementFinding:
    requirement = entry.requirement
    return RequirementFinding(
        document_type=requirement.document_type,
        label=DOCUMENT_TYPE_LABELS[requirement.document_type],
        is_mandatory=requirement.is_mandatory,
        weight=requirement.weight,
        verdict=entry.verdict,
        credit=VERDICT_CREDIT[entry.verdict],
        met=entry.verdict in MET_VERDICTS,
        explanation=_explain(requirement.document_type, entry.verdict),
    )


def _ratio(findings: Iterable[RequirementFinding]) -> Fraction | None:
    """Weighted credit over weight for one band, or `None` when the band has nothing assessed.

    `None` is not zero: a band nobody was asked about must drop out of the blend, not drag it
    down.
    """
    earned = Fraction(0)
    total = 0
    for finding in findings:
        if finding.credit is None:  # not_applicable leaves both sides of the ratio
            continue
        earned += finding.credit * finding.weight
        total += finding.weight
    if total == 0:
        return None
    return earned / total


def _gap_order(finding: RequirementFinding) -> tuple[bool, int, str]:
    """Mandatory before optional, then heaviest first, then by type so ties never reorder."""
    return (not finding.is_mandatory, -finding.weight, finding.document_type.value)


def _select(
    findings: Iterable[RequirementFinding], verdict: DocumentScreeningVerdict
) -> tuple[RequirementFinding, ...]:
    return tuple(sorted((f for f in findings if f.verdict is verdict), key=_gap_order))


def calculate_screening_score(verdicts: Sequence[RequirementVerdict]) -> ScreeningResult:
    """Score one application's checklist. Deterministic: same input, same output, always."""
    findings = tuple(_finding(entry) for entry in verdicts)

    mandatory = [f for f in findings if f.is_mandatory]
    optional = [f for f in findings if not f.is_mandatory]

    mandatory_ratio = _ratio(mandatory)
    optional_ratio = _ratio(optional)

    # An empty band is dropped and the surviving one carries the whole score, rather than being
    # blended against a zero it was never measured on (`docs/09` §8).
    blended: Fraction | None
    if mandatory_ratio is not None and optional_ratio is not None:
        blended = MANDATORY_BAND_WEIGHT * mandatory_ratio + OPTIONAL_BAND_WEIGHT * optional_ratio
    elif mandatory_ratio is not None:
        blended = mandatory_ratio
    elif optional_ratio is not None:
        blended = optional_ratio
    else:
        blended = None

    # Exact rational until this single rounding step. Ties resolve to even, which is arbitrary
    # but fixed — determinism is what the stored score needs.
    score = None if blended is None else round(100 * blended)

    # Totals count assessed requirements only, so they agree with the ratios above and with
    # `ApplicationScreening.has_blocking_gap`, which compares the two stored counts.
    mandatory_total = sum(1 for f in mandatory if f.counted)
    optional_total = sum(1 for f in optional if f.counted)
    mandatory_met = sum(1 for f in mandatory if f.counted and f.met)
    optional_met = sum(1 for f in optional if f.counted and f.met)

    return ScreeningResult(
        score=score,
        mandatory_met=mandatory_met,
        mandatory_total=mandatory_total,
        optional_met=optional_met,
        optional_total=optional_total,
        mandatory_ratio=None if mandatory_ratio is None else float(mandatory_ratio),
        optional_ratio=None if optional_ratio is None else float(optional_ratio),
        findings=findings,
        missing=_select(findings, DocumentScreeningVerdict.MISSING),
        unreadable=_select(findings, DocumentScreeningVerdict.PRESENT_UNREADABLE),
        has_blocking_gap=mandatory_met < mandatory_total,
    )
