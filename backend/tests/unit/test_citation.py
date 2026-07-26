"""Citation verification: exact, normalized, fuzzy, and rejection."""

from __future__ import annotations

import pytest

from app.domain.citation import FUZZY_THRESHOLD, verify_quote
from app.domain.enums import CitationMatchMethod

PAGE = (
    "Section 4.2 Certification. The bidder shall maintain a valid ISO 9001 certificate "
    "for the full duration of the contract, and shall provide the certificate on request."
)


def test_exact_quote_verifies() -> None:
    result = verify_quote(
        quote="The bidder shall maintain a valid ISO 9001 certificate", page_text=PAGE
    )
    assert result.verified is True
    assert result.method is CitationMatchMethod.EXACT
    assert result.score == 1.0


def test_normalized_quote_verifies_across_typographic_differences() -> None:
    # Curly quotes and an en dash in the quote, straight text on the page.
    page = "The contractor shall submit the bid — no later than 30 days — with all documents."
    quote = "shall submit the bid – no later than 30 days"  # en dash variant
    result = verify_quote(quote=quote, page_text=page)
    assert result.verified is True
    assert result.method is CitationMatchMethod.NORMALIZED


def test_case_and_whitespace_differences_normalize() -> None:
    result = verify_quote(
        quote="the  BIDDER shall\nmaintain a valid iso 9001 certificate", page_text=PAGE
    )
    assert result.verified is True
    assert result.method is CitationMatchMethod.NORMALIZED


def test_minor_drift_matches_fuzzily_above_threshold() -> None:
    # One transposed/altered character in a long quote — OCR-style drift.
    quote = "The bidder shall maintain a valid ISO 9001 certifcate for the full duration"
    result = verify_quote(quote=quote, page_text=PAGE)
    assert result.verified is True
    assert result.method is CitationMatchMethod.FUZZY
    assert result.score is not None and result.score >= FUZZY_THRESHOLD


def test_unrelated_quote_is_rejected() -> None:
    result = verify_quote(
        quote="The supplier must provide a performance bond of ten percent", page_text=PAGE
    )
    assert result.verified is False
    assert result.method is CitationMatchMethod.REJECTED


def test_hallucinated_quote_not_on_page_is_rejected() -> None:
    result = verify_quote(
        quote="The bidder shall hold a Grade A safety rating from the authority " * 2,
        page_text=PAGE,
    )
    assert result.verified is False


@pytest.mark.parametrize("empty", ["", "   "])
def test_empty_quote_or_page_is_rejected(empty: str) -> None:
    assert verify_quote(quote=empty, page_text=PAGE).verified is False
    assert verify_quote(quote="anything", page_text=empty).verified is False


def test_short_quote_uses_only_exact_or_normalized() -> None:
    # Below the fuzzy minimum: an exact match still verifies, but a near-miss is rejected
    # rather than fuzzily accepted (short strings match too much).
    assert verify_quote(quote="ISO 9001", page_text=PAGE).verified is True
    assert verify_quote(quote="ISO 9002", page_text=PAGE).method is CitationMatchMethod.REJECTED
