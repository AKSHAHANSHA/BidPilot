"""Page-aware PDF text extraction with quality assessment.

Pure functions over bytes: no database, no storage, no event loop. PyMuPDF is synchronous and
CPU-bound, so the caller runs :func:`extract_pdf_pages` inside `asyncio.to_thread`.

Provenance rule: page numbers are 1-based and preserved exactly — every downstream citation
refers to these numbers, and an off-by-one here would silently corrupt every citation the
pipeline ever verifies.
"""

from __future__ import annotations

from dataclasses import dataclass

import pymupdf

from app.api.errors import AppError
from app.documents.normalize import normalize_text

#: Below this many characters a page is treated as effectively textless — a scanned image,
#: a cover page, or a decorative divider.
MIN_PAGE_CHARACTERS = 40

#: A document is usable when at least this fraction of pages carries real text. A brochure
#: with one text page out of forty is not analysable evidence.
MIN_TEXTUAL_PAGE_RATIO = 0.3


class PdfParseError(AppError):
    """The bytes passed magic-byte validation but PyMuPDF cannot read them."""

    status = 422
    code = "DOCUMENT_UNREADABLE"
    title = "Document unreadable"
    slug = "document-unreadable"


class PdfTooManyPagesError(AppError):
    status = 422
    code = "DOCUMENT_TOO_MANY_PAGES"
    title = "Document too large"
    slug = "document-too-many-pages"


@dataclass(frozen=True, slots=True)
class ExtractedPage:
    page_number: int  # 1-based
    text: str
    normalized_text: str
    character_count: int
    quality_score: float
    extraction_method: str


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    pages: tuple[ExtractedPage, ...]
    page_count: int
    #: False when the document is effectively textless (scanned or image-only). The caller
    #: records `unsupported` instead of pretending empty pages are analysable.
    is_text_extractable: bool
    textual_page_ratio: float


def score_page_quality(text: str) -> float:
    """Heuristic 0-1 score for how usable a page's text is.

    Two signals: enough characters to carry meaning, and a sane ratio of word characters to
    total (garbled CID-font extractions produce soup with low word-character density). This is
    a triage signal for the pipeline and the UI, not a truth claim.
    """
    stripped = text.strip()
    if len(stripped) < MIN_PAGE_CHARACTERS:
        return 0.0

    word_chars = sum(1 for ch in stripped if ch.isalnum() or ch.isspace())
    density = word_chars / len(stripped)

    # Volume component saturates at ~1500 chars — a typical full page of contract text.
    volume = min(len(stripped) / 1500.0, 1.0)

    return round(min(density, 1.0) * 0.6 + volume * 0.4, 2)


def extract_pdf_pages(content: bytes, *, max_pages: int) -> ExtractionResult:
    """Extract every page's text, preserving 1-based numbering.

    Raises :class:`PdfParseError` for corrupt or encrypted documents and
    :class:`PdfTooManyPagesError` beyond the configured bound.
    """
    try:
        document = pymupdf.open(stream=content, filetype="pdf")
    except Exception as exc:  # PyMuPDF raises various internal error types
        raise PdfParseError("The PDF could not be parsed. It may be corrupt or truncated.") from exc

    try:
        if document.needs_pass:
            raise PdfParseError("The PDF is password-protected and cannot be processed.")

        if document.page_count > max_pages:
            raise PdfTooManyPagesError(
                f"The PDF has {document.page_count} pages; the maximum is {max_pages}."
            )

        pages: list[ExtractedPage] = []
        for index in range(document.page_count):
            raw = document[index].get_text("text")
            normalized = normalize_text(raw)
            pages.append(
                ExtractedPage(
                    page_number=index + 1,
                    text=raw,
                    normalized_text=normalized,
                    character_count=len(normalized),
                    quality_score=score_page_quality(normalized),
                    extraction_method="native",
                )
            )
    finally:
        document.close()

    textual = sum(1 for page in pages if page.character_count >= MIN_PAGE_CHARACTERS)
    ratio = textual / len(pages) if pages else 0.0

    return ExtractionResult(
        pages=tuple(pages),
        page_count=len(pages),
        is_text_extractable=bool(pages) and ratio >= MIN_TEXTUAL_PAGE_RATIO,
        textual_page_ratio=round(ratio, 3),
    )
