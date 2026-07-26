"""Page-aware extraction: numbering, normalization, quality, and failure modes."""

from __future__ import annotations

import pymupdf
import pytest

from app.documents.extraction import (
    MIN_PAGE_CHARACTERS,
    ExtractionResult,
    PdfParseError,
    PdfTooManyPagesError,
    extract_pdf_pages,
    score_page_quality,
)
from app.documents.normalize import normalize_text


def make_pdf(*page_texts: str, password: str | None = None) -> bytes:
    document = pymupdf.open()
    for text in page_texts or ("",):
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text, fontsize=11)
    if password:
        content = document.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw=password)
    else:
        content = document.tobytes()
    document.close()
    return bytes(content)


LONG = (
    "The bidder shall maintain a valid ISO 9001 certificate for the duration of the "
    "contract and shall provide evidence of renewal not later than thirty days before expiry."
)


# --- Normalization -------------------------------------------------------------------------


def test_normalize_unifies_quotes_dashes_and_whitespace() -> None:
    raw = "The “bidder” shall – without delay — submit\n\nits  ‘bid’."
    assert normalize_text(raw) == "The \"bidder\" shall - without delay - submit its 'bid'."


def test_normalize_preserves_case() -> None:
    # Case-insensitive comparison happens at match time (Phase 7); the stored page stays
    # readable in the source viewer.
    assert normalize_text("The BIDDER Shall") == "The BIDDER Shall"


# --- Extraction ----------------------------------------------------------------------------


def extract(*texts: str, max_pages: int = 200) -> ExtractionResult:
    return extract_pdf_pages(make_pdf(*texts), max_pages=max_pages)


def test_page_numbers_are_one_based_and_preserved() -> None:
    result = extract("Page one " + LONG, "Page two " + LONG, "Page three " + LONG)
    assert result.page_count == 3
    assert [p.page_number for p in result.pages] == [1, 2, 3]
    assert "Page two" in result.pages[1].text
    assert "Page two" in result.pages[1].normalized_text


def test_text_pdf_is_extractable(caplog: pytest.LogCaptureFixture) -> None:
    result = extract(LONG, LONG)
    assert result.is_text_extractable is True
    assert result.textual_page_ratio == 1.0
    assert all(p.quality_score > 0 for p in result.pages)


def test_fully_empty_pdf_is_flagged_unsupported() -> None:
    result = extract("", "", "")
    assert result.page_count == 3
    assert result.is_text_extractable is False
    assert all(p.quality_score == 0.0 for p in result.pages)


def test_mostly_empty_pdf_is_flagged_unsupported() -> None:
    # One text page in five is below the usable ratio — a scanned document with a text cover.
    result = extract(LONG, "", "", "", "")
    assert result.is_text_extractable is False
    assert result.textual_page_ratio == 0.2


def test_too_many_pages_is_rejected() -> None:
    with pytest.raises(PdfTooManyPagesError):
        extract(LONG, LONG, LONG, max_pages=2)


def test_corrupt_pdf_is_rejected() -> None:
    with pytest.raises(PdfParseError, match="corrupt or truncated"):
        extract_pdf_pages(b"%PDF-1.7 garbage that is not a pdf body", max_pages=10)


def test_password_protected_pdf_is_rejected() -> None:
    content = make_pdf(LONG, password="secret")
    with pytest.raises(PdfParseError, match="password-protected"):
        extract_pdf_pages(content, max_pages=10)


# --- Quality scoring -------------------------------------------------------------------------


def test_short_text_scores_zero() -> None:
    assert score_page_quality("x" * (MIN_PAGE_CHARACTERS - 1)) == 0.0


def test_real_prose_scores_high() -> None:
    assert score_page_quality(LONG * 10) > 0.8


def test_garbled_soup_scores_lower_than_prose() -> None:
    soup = "Þ¶¤#@!$%^&*(){}[]|\\<>~`" * 20
    assert score_page_quality(soup) < score_page_quality(LONG * 3)


def test_quality_is_bounded() -> None:
    for text in ("", LONG, LONG * 100, "@#$%" * 500):
        assert 0.0 <= score_page_quality(text) <= 1.0
