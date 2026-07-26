"""Citation verification: does the quote actually appear on the cited page?

Pure functions over text — no I/O, no database — so the rules are directly testable and
deterministic (`docs/03` §6). A requirement becomes canonical only when a citation verifies
against the extracted page text; "not found" rejects the citation, it does not invent absence.

Three tiers, tried in order:

1. **exact** — the quote appears verbatim in the raw page text.
2. **normalized** — the quote appears after both sides pass through `normalize_text` (the same
   normalizer that produced `document_pages.normalized_text`) and are lower-cased. This absorbs
   curly quotes, dashes, and whitespace differences.
3. **fuzzy** — a bounded token-similarity fallback for OCR-ish drift, accepted only above a
   documented threshold. Below it, the citation is rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from app.documents.normalize import normalize_text
from app.domain.enums import CitationMatchMethod

#: A fuzzy match at or above this ratio is accepted; below it the citation is rejected. Chosen
#: to tolerate minor extraction drift while rejecting a quote that is merely on the same topic.
FUZZY_THRESHOLD = 0.90

#: A quote shorter than this is too weak to fuzzy-match safely (short strings match many
#: things), so only exact/normalized matching applies to it.
MIN_FUZZY_QUOTE_CHARS = 25


@dataclass(frozen=True, slots=True)
class VerificationResult:
    verified: bool
    method: CitationMatchMethod
    score: float | None

    @property
    def is_canonical(self) -> bool:
        return self.verified


def _prep(text: str) -> str:
    return normalize_text(text).casefold()


def verify_quote(*, quote: str, page_text: str) -> VerificationResult:
    """Classify how well `quote` is supported by `page_text`."""
    if not quote.strip() or not page_text.strip():
        return VerificationResult(False, CitationMatchMethod.REJECTED, None)

    # Tier 1: exact substring in the raw text.
    if quote in page_text:
        return VerificationResult(True, CitationMatchMethod.EXACT, 1.0)

    # Tier 2: normalized substring (curly quotes, dashes, whitespace, case).
    norm_quote = _prep(quote)
    norm_page = _prep(page_text)
    if norm_quote and norm_quote in norm_page:
        return VerificationResult(True, CitationMatchMethod.NORMALIZED, 1.0)

    # Tier 3: bounded fuzzy, only for quotes long enough to be discriminating.
    if len(norm_quote) >= MIN_FUZZY_QUOTE_CHARS:
        score = _best_window_ratio(norm_quote, norm_page)
        if score >= FUZZY_THRESHOLD:
            return VerificationResult(True, CitationMatchMethod.FUZZY, round(score, 3))
        return VerificationResult(False, CitationMatchMethod.REJECTED, round(score, 3))

    return VerificationResult(False, CitationMatchMethod.REJECTED, None)


def _best_window_ratio(needle: str, haystack: str) -> float:
    """Similarity of `needle` against the region of `haystack` where it best aligns.

    A whole-page ratio would be diluted by surrounding text, and a fixed-length sliding window
    mis-aligns as soon as the quote has an inserted or deleted character. Instead, locate the
    longest common block, align a needle-sized window (with a small margin for length drift) to
    it, and score there — so a one-character OCR difference still reads as a near-perfect match.
    """
    if not haystack:
        return 0.0
    if len(needle) >= len(haystack):
        return SequenceMatcher(None, needle, haystack, autojunk=False).ratio()

    matcher = SequenceMatcher(None, needle, haystack, autojunk=False)
    match = matcher.find_longest_match(0, len(needle), 0, len(haystack))
    if match.size == 0:
        return 0.0

    # Where the needle would start in the haystack, given the aligned block.
    start = max(0, match.b - match.a)
    margin = 5  # absorbs a few insertions/deletions relative to the quote length
    segment = haystack[start : start + len(needle) + margin]
    return SequenceMatcher(None, needle, segment, autojunk=False).ratio()
