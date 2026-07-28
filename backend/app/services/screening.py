"""Deterministic vendor-application screening.

Pure functions over the project text and the vendor's supplied signals (cover letter,
optional uploaded document name, and vendor category). Produces a 0..100 score with a
short plain-English summary.

Rules — same principles as the bid-readiness scorer (`app/domain/scoring.py`):
- Score is computed here in Python, never by an LLM.
- Category alignment is the strongest positive signal.
- Description keyword overlap with the vendor's cover letter is a weaker positive.
- Missing evidence of certifications named in the project text yields negative points.
- Score is clamped to 0..100 and every component contributing to it is returned so the
  UI can render an explainable breakdown.

Deliberately conservative: the demo AI screening never claims a vendor is a definitive fit,
only that "on the evidence supplied, the match score is X".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_WORD_RE = re.compile(r"[a-z0-9]{3,}")
_STOPWORDS: frozenset[str] = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "are",
        "was",
        "this",
        "that",
        "have",
        "has",
        "our",
        "your",
        "will",
        "not",
        "any",
        "all",
        "into",
        "over",
        "under",
        "per",
    }
)

_CERTIFICATIONS = (
    "iso 9001",
    "iso 14001",
    "iso 27001",
    "iso 22000",
    "iso 41001",
    "iso 45001",
    "haccp",
    "sira",
    "haad",
    "moh",
    "hipaa",
    "hl7",
    "fhir",
    "dicom",
    "oeko-tex",
    "icao",
)


@dataclass(frozen=True, slots=True)
class ScreeningInput:
    project_title: str
    project_description: str
    project_category: str
    project_requirements: str | None
    vendor_category: str | None
    vendor_bio: str | None
    cover_letter: str | None
    document_original_name: str | None


@dataclass(frozen=True, slots=True)
class ScreeningResult:
    score: int
    summary: str
    breakdown: dict[str, Any]


def _tokenize(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS}


def _mentioned_certifications(text: str) -> set[str]:
    lowered = text.lower()
    return {cert for cert in _CERTIFICATIONS if cert in lowered}


def screen_application(payload: ScreeningInput) -> ScreeningResult:
    """Compute an explainable 0..100 fit score."""
    reasons: list[str] = []

    # Category alignment: strongest single signal (30 points).
    category_match = (
        payload.vendor_category is not None
        and payload.vendor_category == payload.project_category
    )
    category_score = 30 if category_match else 10
    if category_match:
        reasons.append("Vendor's primary category matches the project category.")
    else:
        reasons.append(
            "Vendor's primary category does not exactly match the project category."
        )

    # Keyword overlap between the vendor's cover letter/bio and the project text (0..25).
    project_terms = _tokenize(
        " ".join(
            [
                payload.project_title,
                payload.project_description,
                payload.project_requirements or "",
            ]
        )
    )
    vendor_terms = _tokenize(" ".join([payload.vendor_bio or "", payload.cover_letter or ""]))
    overlap = project_terms & vendor_terms
    keyword_score = min(len(overlap), 25)
    if overlap:
        sample = sorted(overlap)[:6]
        reasons.append(
            f"Matched keywords in the vendor's submission: {', '.join(sample)}"
            + ("…" if len(overlap) > 6 else ".")
        )
    else:
        reasons.append(
            "No overlapping keywords between the project and the vendor's supplied text."
        )

    # Certification coverage: which certifications named in the project are ALSO named
    # by the vendor's supplied text or document filename (0..25).
    required_certs = _mentioned_certifications(
        " ".join([payload.project_description, payload.project_requirements or ""])
    )
    supplied = _mentioned_certifications(
        " ".join(
            [
                payload.vendor_bio or "",
                payload.cover_letter or "",
                payload.document_original_name or "",
            ]
        )
    )
    if required_certs:
        covered = required_certs & supplied
        coverage_ratio = len(covered) / len(required_certs)
        cert_score = int(round(25 * coverage_ratio))
        if coverage_ratio == 1:
            reasons.append(
                f"All named certifications appear in the vendor's submission: "
                f"{', '.join(sorted(covered))}."
            )
        elif coverage_ratio > 0:
            missing = sorted(required_certs - supplied)
            reasons.append(
                "Partial certification coverage; missing "
                + ", ".join(missing[:4])
                + ("…" if len(missing) > 4 else "")
                + "."
            )
        else:
            reasons.append(
                "None of the certifications named in the project are evidenced by the "
                "vendor's submission."
            )
    else:
        cert_score = 15  # neutral credit when the project text names no certs
        reasons.append("Project does not name specific certifications; neutral credit applied.")

    # Document supplied at all: 10 or 0.
    if payload.document_original_name:
        document_score = 10
        reasons.append(
            f"Supporting document supplied: {payload.document_original_name}."
        )
    else:
        document_score = 0
        reasons.append("No supporting document uploaded; add credentials to raise the score.")

    # Cover letter length: 0..10 for a substantive letter.
    letter_len = len(payload.cover_letter or "")
    if letter_len >= 400:
        letter_score = 10
        reasons.append("Cover letter provides substantive detail.")
    elif letter_len >= 100:
        letter_score = 5
        reasons.append("Cover letter is short; expanding it would help the assessment.")
    else:
        letter_score = 0
        reasons.append("No meaningful cover letter provided.")

    raw = category_score + keyword_score + cert_score + document_score + letter_score
    score = max(0, min(100, raw))

    breakdown = {
        "category_score": category_score,
        "keyword_score": keyword_score,
        "certification_score": cert_score,
        "document_score": document_score,
        "cover_letter_score": letter_score,
        "matched_keywords": sorted(overlap)[:12],
        "required_certifications": sorted(required_certs),
        "supplied_certifications": sorted(supplied),
        "reasons": reasons,
        "algorithm_version": "1.0.0",
    }

    if score >= 80:
        summary_prefix = "Strong fit"
    elif score >= 60:
        summary_prefix = "Moderate fit"
    elif score >= 40:
        summary_prefix = "Partial fit"
    else:
        summary_prefix = "Weak fit"

    summary = (
        f"{summary_prefix} ({score}/100). "
        + " ".join(reasons[:3])
    )

    return ScreeningResult(score=score, summary=summary, breakdown=breakdown)
