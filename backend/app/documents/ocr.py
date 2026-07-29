"""OCR fallback for PDF pages that carry their content as an image rather than as text.

`app/documents/extraction.py` reads whatever text layer a PDF actually has. Scanned trade
licences, stamped certificates and photographed insurance schedules have none, and the vendor
who uploaded them is not wrong — the document is real, we simply cannot read it. §7 of
`docs/09_PORTAL_SPEC.md` makes that distinction load-bearing: an unreadable page is reported
as "could not be read", never as "missing", because the two demand different actions from the
vendor.

That is why nothing here ever returns an empty string for a page. A page that OCR did not
recognise is absent from :attr:`OcrResult.text_by_page` and named in `skipped_pages` or
`unread_pages`; a caller therefore cannot mistake "we failed" for "this page is blank".

OCR depends on a system binary, so it is optional by construction: :class:`NullOcrEngine` is
the default and :func:`build_ocr_engine` downgrades to it loudly. Recognition itself is
CPU-bound and shells out, so it runs inside `asyncio.to_thread` exactly like `app/storage/local.py`.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Protocol

import pymupdf

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)

#: Looked up on PATH. PyMuPDF's own `get_textpage_ocr` was measured working on the build
#: machine, but its Tesseract is linked into MuPDF and finds its language data through
#: `TESSDATA_PREFIX`, which this deployment does not set. Availability would then no longer
#: mean what `shutil.which` reports, and the only fix — mutating `os.environ` from a library
#: inside a threaded worker — is worse than one subprocess per page.
TESSERACT_BINARY: Final = "tesseract"

TESSERACT_ENGINE: Final = "tesseract"
NULL_ENGINE: Final = "null"

#: Per page, not per document. Tesseract on a 300-DPI A4 scan takes ~2s; a minute means the
#: process is wedged and the screening job must not wait on it.
PAGE_TIMEOUT_SECONDS: Final = 60.0

#: Enough of Tesseract's diagnostics to identify the failure, not enough to smuggle recognised
#: document text into the log.
_STDERR_LOG_LIMIT: Final = 200


@dataclass(frozen=True, slots=True)
class OcrResult:
    """What OCR read, and — kept deliberately separate — what it did not.

    `text_by_page` maps a 1-based page number to recognised text and never holds an empty
    value: a page is present only when OCR produced something. Every requested page that is
    absent appears in exactly one of the two failure tuples, so the caller can count
    `pages_needing_ocr` without inferring anything.
    """

    engine: str
    text_by_page: Mapping[int, str]
    #: Requested but never attempted: no engine is available, or `settings.ocr_max_pages` was
    #: already spent. Re-running with OCR enabled or a higher cap would read these.
    skipped_pages: tuple[int, ...]
    #: Attempted, and no text came back — recognition produced nothing legible, the render or
    #: the binary failed, or the page is not in the document. Never a claim that the page is
    #: blank: OCR cannot tell an empty page from one it failed on, so neither can we.
    unread_pages: tuple[int, ...]

    @property
    def pages_without_text(self) -> tuple[int, ...]:
        """Every requested page OCR could not supply text for. This is `pages_needing_ocr`."""
        return tuple(sorted(set(self.skipped_pages) | set(self.unread_pages)))


class OcrEngine(Protocol):
    """Structural interface, like `app/storage/base.py` — no base class to inherit."""

    @property
    def available(self) -> bool:
        """True when this engine can actually recognise text right now.

        False is a normal operating state, not an error: the caller records the pages it could
        not read and continues.
        """
        ...

    async def recognize_pages(self, content: bytes, *, page_numbers: Sequence[int]) -> OcrResult:
        """Recognise text on the given 1-based pages of `content`.

        Implementations never raise for a page they cannot read — a bad page is reported in the
        result — and never invent text. Returned text is raw recognition output; normalization
        is the caller's, so the same `app/documents/normalize.py` runs over native and OCR text.
        """
        ...


class NullOcrEngine:
    """The default engine: reads nothing and says so.

    It reports every requested page as skipped rather than returning blank text, which is the
    whole point — with no OCR configured those pages are unknown, not empty.
    """

    @property
    def available(self) -> bool:
        return False

    async def recognize_pages(self, content: bytes, *, page_numbers: Sequence[int]) -> OcrResult:
        return OcrResult(
            engine=NULL_ENGINE,
            text_by_page={},
            skipped_pages=_ordered_unique(page_numbers),
            unread_pages=(),
        )


class TesseractOcrEngine:
    """Renders each page with PyMuPDF and pipes the image through the `tesseract` binary."""

    def __init__(self, settings: Settings) -> None:
        # Construction must never raise. The engine is built wherever screening runs, and a
        # machine without Tesseract is a degraded mode we report, not a startup failure.
        self._binary = shutil.which(TESSERACT_BINARY)
        self._languages = settings.ocr_languages
        self._dpi = settings.ocr_dpi
        self._max_pages = settings.ocr_max_pages

    @property
    def available(self) -> bool:
        return self._binary is not None

    async def recognize_pages(self, content: bytes, *, page_numbers: Sequence[int]) -> OcrResult:
        requested = _ordered_unique(page_numbers)

        if self._binary is None:
            # Reachable when settings changed or the binary vanished after construction.
            return OcrResult(
                engine=TESSERACT_ENGINE,
                text_by_page={},
                skipped_pages=requested,
                unread_pages=(),
            )

        attempted = requested[: self._max_pages]
        capped = requested[self._max_pages :]
        if capped:
            logger.warning(
                "ocr.page_cap_reached",
                extra={"max_pages": self._max_pages, "skipped_pages": list(capped)},
            )

        recognized, unread = await asyncio.to_thread(
            self._recognize_blocking, self._binary, content, attempted
        )

        logger.info(
            "ocr.completed",
            extra={
                "requested_pages": len(requested),
                "recognized_pages": len(recognized),
                "unread_pages": len(unread),
                "skipped_pages": len(capped),
            },
        )
        return OcrResult(
            engine=TESSERACT_ENGINE,
            text_by_page=recognized,
            skipped_pages=capped,
            unread_pages=tuple(unread),
        )

    def _recognize_blocking(
        self, binary: str, content: bytes, page_numbers: Sequence[int]
    ) -> tuple[dict[int, str], list[int]]:
        """Render and recognise, synchronously. Runs in a worker thread."""
        if not page_numbers:
            return {}, []

        try:
            document = pymupdf.open(stream=content, filetype="pdf")
        except Exception as exc:  # PyMuPDF raises various internal error types
            # Extraction has already parsed these bytes once, so this is close to impossible;
            # if it happens, the pages are unknown rather than empty.
            logger.warning("ocr.document_unreadable", extra={"error": str(exc)})
            return {}, list(page_numbers)

        recognized: dict[int, str] = {}
        unread: list[int] = []
        try:
            for number in page_numbers:
                if not 1 <= number <= document.page_count:
                    # A page number outside the document is a caller bug. Report it; never
                    # substitute a neighbouring page's text for it.
                    logger.warning(
                        "ocr.page_out_of_range",
                        extra={"page_number": number, "page_count": document.page_count},
                    )
                    unread.append(number)
                    continue

                image = document[number - 1].get_pixmap(dpi=self._dpi).tobytes("png")
                text = self._run_tesseract(binary, image)
                if text:
                    recognized[number] = text
                else:
                    unread.append(number)
        finally:
            document.close()

        return recognized, unread

    def _run_tesseract(self, binary: str, image: bytes) -> str:
        """Return recognised text, or an empty string when the page could not be read.

        The caller turns that empty string into an `unread_pages` entry — it never becomes a
        stored page of blank text.
        """
        command = [
            binary,
            "-",  # read the image from stdin: no temp file to leak or clean up
            "stdout",
            "-l",
            self._languages,
            "--dpi",
            str(self._dpi),
        ]
        try:
            # Fixed argv, absolute path from `shutil.which`, no shell: the untrusted document
            # travels on stdin as bytes and is never part of the command line.
            completed = subprocess.run(  # noqa: S603
                command,
                input=image,
                capture_output=True,
                timeout=PAGE_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("ocr.page_failed", extra={"reason": type(exc).__name__})
            return ""

        if completed.returncode != 0:
            logger.warning(
                "ocr.tesseract_failed",
                extra={
                    "returncode": completed.returncode,
                    "stderr": completed.stderr.decode("utf-8", errors="replace")[
                        :_STDERR_LOG_LIMIT
                    ],
                },
            )
            return ""

        return completed.stdout.decode("utf-8", errors="replace").strip()


def needs_ocr(native_text: str, *, min_chars: int) -> bool:
    """True when a page's native text is too thin to be real content.

    Measured on the stripped string: PyMuPDF hands back whitespace and form feeds for an
    image-only page, and counting those as content would skip the pages OCR exists for.
    """
    return len(native_text.strip()) < min_chars


def build_ocr_engine(settings: Settings) -> OcrEngine:
    """Choose the engine and record why.

    A silent downgrade to Null looks identical to "every document was unreadable", so the
    reason is logged at selection time rather than left to be reconstructed from screening rows.
    """
    if not settings.ocr_enabled:
        logger.info("ocr.engine_selected", extra={"engine": NULL_ENGINE, "reason": "disabled"})
        return NullOcrEngine()

    engine = TesseractOcrEngine(settings)
    if not engine.available:
        logger.warning(
            "ocr.engine_selected",
            extra={"engine": NULL_ENGINE, "reason": "tesseract_binary_not_found"},
        )
        return NullOcrEngine()

    logger.info(
        "ocr.engine_selected",
        extra={
            "engine": TESSERACT_ENGINE,
            "reason": "enabled_and_available",
            "languages": settings.ocr_languages,
            "dpi": settings.ocr_dpi,
        },
    )
    return engine


def _ordered_unique(page_numbers: Iterable[int]) -> tuple[int, ...]:
    """De-duplicate while preserving order, so the page cap is applied to real work only."""
    seen: set[int] = set()
    ordered: list[int] = []
    for number in page_numbers:
        if number not in seen:
            seen.add(number)
            ordered.append(number)
    return tuple(ordered)
