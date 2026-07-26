"""Text normalization shared by page storage (Phase 4) and citation matching (Phase 7).

One implementation on purpose: a quote is verified against a page by comparing *normalized*
forms, so the normalizer that wrote `document_pages.normalized_text` must be the same one that
processes the model's quotes. Two normalizers would reintroduce the exact mismatch class this
exists to remove.
"""

from __future__ import annotations

import re
import unicodedata

#: Typographic variants that PDFs love and models reproduce inconsistently.
_CHAR_MAP = str.maketrans(
    {
        "‘": "'",  # left single quote
        "’": "'",  # right single quote
        "“": '"',  # left double quote
        "”": '"',  # right double quote
        "–": "-",  # en dash
        "—": "-",  # em dash
        "−": "-",  # minus sign
        " ": " ",  # no-break space
        "​": "",  # zero-width space
        "﻿": "",  # BOM
    }
)

_WHITESPACE = re.compile(r"\s+")


def normalize_text(raw: str) -> str:
    """Unicode-normalize, unify quotes/dashes, collapse whitespace. Case is preserved.

    Case-insensitive comparison is applied at match time (Phase 7), not baked into the stored
    text, so the normalized page remains readable in the source viewer.
    """
    text = unicodedata.normalize("NFKC", raw)
    text = text.translate(_CHAR_MAP)
    return _WHITESPACE.sub(" ", text).strip()
