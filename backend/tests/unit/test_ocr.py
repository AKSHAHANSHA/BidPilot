"""OCR engine selection, the page cap, and the unreadable-vs-blank distinction.

Nothing here needs Tesseract installed: `subprocess.run` and `shutil.which` are patched, so the
selection logic, the argv we build, and the failure bookkeeping are all exercised on a machine
with no OCR at all. The single test that genuinely shells out carries the `integration` marker.

The assertions that matter most are the negative ones: a page OCR could not read must never
appear in `text_by_page`, not even as an empty string, because a caller that saw one would
report a scanned certificate to a vendor as a blank page.
"""

from __future__ import annotations

import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any

import pymupdf
import pytest

from app.core.config import Settings
from app.documents import ocr as ocr_module
from app.documents.ocr import (
    NULL_ENGINE,
    TESSERACT_ENGINE,
    NullOcrEngine,
    OcrEngine,
    OcrResult,
    TesseractOcrEngine,
    build_ocr_engine,
    needs_ocr,
)

FAKE_BINARY = "/usr/local/bin/tesseract"

SAMPLE_TENDER = Path(__file__).resolve().parents[2] / "sample_data" / "sample_tender.pdf"


def ocr_settings(settings: Settings, **overrides: Any) -> Settings:
    """Settings with the OCR block pinned, so the developer's `.env` cannot steer a test."""
    base = {"ocr_enabled": True, "ocr_languages": "eng", "ocr_dpi": 300, "ocr_max_pages": 30}
    return settings.model_copy(update={**base, **overrides})


def make_pdf(page_count: int = 1) -> bytes:
    """A PDF with real pages to render. Content is irrelevant — recognition is stubbed."""
    document = pymupdf.open()
    for index in range(page_count):
        document.new_page().insert_text((72, 72), f"page {index + 1}", fontsize=11)
    content = bytes(document.tobytes())
    document.close()
    return content


class FakeTesseract:
    """Stands in for `subprocess.run`, recording every argv and the thread it ran on."""

    def __init__(self, stdout: bytes = b"recognised text", returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.commands: list[list[str]] = []
        self.threads: list[str] = []

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        self.commands.append(command)
        self.threads.append(threading.current_thread().name)
        return subprocess.CompletedProcess(
            args=command, returncode=self.returncode, stdout=self.stdout, stderr=b""
        )


@pytest.fixture
def tesseract(monkeypatch: pytest.MonkeyPatch) -> FakeTesseract:
    """Pretend the binary exists and answer every invocation with canned text."""
    fake = FakeTesseract()
    monkeypatch.setattr(shutil, "which", lambda name: FAKE_BINARY)
    monkeypatch.setattr(ocr_module.subprocess, "run", fake)
    return fake


# --- needs_ocr -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", True),
        ("   \n\f  ", True),  # PyMuPDF's answer for an image-only page
        ("short", True),
        ("x" * 39, True),
        ("x" * 40, False),
        ("x" * 4000, False),
    ],
)
def test_needs_ocr_uses_stripped_length(text: str, expected: bool) -> None:
    assert needs_ocr(text, min_chars=40) is expected


def test_needs_ocr_min_chars_zero_never_triggers() -> None:
    # A deployment that sets the floor to 0 has opted out of OCR by configuration.
    assert needs_ocr("", min_chars=0) is False


# --- NullOcrEngine -------------------------------------------------------------------------


async def test_null_engine_is_unavailable_and_reads_nothing() -> None:
    engine = NullOcrEngine()
    assert engine.available is False

    result = await engine.recognize_pages(make_pdf(3), page_numbers=[1, 2, 3])

    assert result.engine == NULL_ENGINE
    assert dict(result.text_by_page) == {}
    assert result.skipped_pages == (1, 2, 3)
    assert result.unread_pages == ()
    assert result.pages_without_text == (1, 2, 3)


async def test_null_engine_deduplicates_requested_pages() -> None:
    result = await NullOcrEngine().recognize_pages(make_pdf(), page_numbers=[2, 1, 2])
    assert result.skipped_pages == (2, 1)


def test_both_engines_satisfy_the_protocol(settings: Settings) -> None:
    # Structural, not inherited: the annotation is the real assertion — mypy rejects this list
    # if either class drifts from the protocol.
    engines: list[OcrEngine] = [NullOcrEngine(), TesseractOcrEngine(ocr_settings(settings))]
    assert engines[0].available is False


# --- OcrResult -----------------------------------------------------------------------------


def test_pages_without_text_merges_both_failure_kinds() -> None:
    result = OcrResult(
        engine=TESSERACT_ENGINE,
        text_by_page={2: "text"},
        skipped_pages=(5, 4),
        unread_pages=(1, 4),
    )
    assert result.pages_without_text == (1, 4, 5)


# --- build_ocr_engine ----------------------------------------------------------------------


def test_build_returns_null_when_ocr_disabled(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: FAKE_BINARY)
    assert isinstance(build_ocr_engine(ocr_settings(settings, ocr_enabled=False)), NullOcrEngine)


def test_build_returns_null_when_binary_missing(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert isinstance(build_ocr_engine(ocr_settings(settings)), NullOcrEngine)


def test_build_returns_tesseract_when_enabled_and_present(
    settings: Settings, tesseract: FakeTesseract
) -> None:
    engine = build_ocr_engine(ocr_settings(settings))
    assert isinstance(engine, TesseractOcrEngine)
    assert engine.available is True


# --- TesseractOcrEngine: absent binary -----------------------------------------------------


def test_construction_never_raises_without_the_binary(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    engine = TesseractOcrEngine(ocr_settings(settings))
    assert engine.available is False


async def test_unavailable_engine_skips_every_page(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    engine = TesseractOcrEngine(ocr_settings(settings))

    result = await engine.recognize_pages(make_pdf(2), page_numbers=[1, 2])

    assert dict(result.text_by_page) == {}
    assert result.skipped_pages == (1, 2)


# --- TesseractOcrEngine: recognition -------------------------------------------------------


async def test_recognized_pages_keep_one_based_numbering(
    settings: Settings, tesseract: FakeTesseract
) -> None:
    engine = TesseractOcrEngine(ocr_settings(settings))

    result = await engine.recognize_pages(make_pdf(3), page_numbers=[1, 3])

    assert result.engine == TESSERACT_ENGINE
    assert dict(result.text_by_page) == {1: "recognised text", 3: "recognised text"}
    assert result.pages_without_text == ()
    assert len(tesseract.commands) == 2


async def test_command_honours_language_and_dpi_settings(
    settings: Settings, tesseract: FakeTesseract
) -> None:
    engine = TesseractOcrEngine(ocr_settings(settings, ocr_languages="eng+ara", ocr_dpi=200))

    await engine.recognize_pages(make_pdf(), page_numbers=[1])

    assert tesseract.commands == [[FAKE_BINARY, "-", "stdout", "-l", "eng+ara", "--dpi", "200"]]


async def test_blocking_work_leaves_the_event_loop(
    settings: Settings, tesseract: FakeTesseract
) -> None:
    engine = TesseractOcrEngine(ocr_settings(settings))

    await engine.recognize_pages(make_pdf(), page_numbers=[1])

    assert tesseract.threads and threading.main_thread().name not in tesseract.threads


async def test_page_cap_reports_the_pages_it_refused(
    settings: Settings, tesseract: FakeTesseract
) -> None:
    engine = TesseractOcrEngine(ocr_settings(settings, ocr_max_pages=2))

    result = await engine.recognize_pages(make_pdf(4), page_numbers=[1, 2, 3, 4])

    assert sorted(result.text_by_page) == [1, 2]
    assert result.skipped_pages == (3, 4)
    assert result.unread_pages == ()
    # The cap bounds real work, not just the reported set.
    assert len(tesseract.commands) == 2


async def test_duplicate_requests_are_not_charged_against_the_cap(
    settings: Settings, tesseract: FakeTesseract
) -> None:
    engine = TesseractOcrEngine(ocr_settings(settings, ocr_max_pages=2))

    result = await engine.recognize_pages(make_pdf(3), page_numbers=[1, 1, 2, 3])

    assert sorted(result.text_by_page) == [1, 2]
    assert result.skipped_pages == (3,)


async def test_empty_request_does_no_work(settings: Settings, tesseract: FakeTesseract) -> None:
    result = await TesseractOcrEngine(ocr_settings(settings)).recognize_pages(
        make_pdf(), page_numbers=[]
    )

    assert dict(result.text_by_page) == {}
    assert result.pages_without_text == ()
    assert tesseract.commands == []


# --- TesseractOcrEngine: never fabricating text --------------------------------------------


async def test_page_with_no_recognised_text_is_unread_not_blank(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Tesseract exits 0 with empty output for a page it cannot make sense of. That is not
    # evidence the page is blank, so it must not become a stored empty page.
    fake = FakeTesseract(stdout=b"  \n \n")
    monkeypatch.setattr(shutil, "which", lambda name: FAKE_BINARY)
    monkeypatch.setattr(ocr_module.subprocess, "run", fake)

    result = await TesseractOcrEngine(ocr_settings(settings)).recognize_pages(
        make_pdf(), page_numbers=[1]
    )

    assert dict(result.text_by_page) == {}
    assert result.unread_pages == (1,)


async def test_nonzero_exit_marks_the_page_unread(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeTesseract(stdout=b"", returncode=1)
    monkeypatch.setattr(shutil, "which", lambda name: FAKE_BINARY)
    monkeypatch.setattr(ocr_module.subprocess, "run", fake)

    result = await TesseractOcrEngine(ocr_settings(settings)).recognize_pages(
        make_pdf(2), page_numbers=[1, 2]
    )

    assert dict(result.text_by_page) == {}
    assert result.unread_pages == (1, 2)


@pytest.mark.parametrize(
    "failure", [OSError("binary vanished"), subprocess.TimeoutExpired(cmd="tesseract", timeout=60)]
)
async def test_subprocess_failures_do_not_escape(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    def explode(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        raise failure

    monkeypatch.setattr(shutil, "which", lambda name: FAKE_BINARY)
    monkeypatch.setattr(ocr_module.subprocess, "run", explode)

    result = await TesseractOcrEngine(ocr_settings(settings)).recognize_pages(
        make_pdf(), page_numbers=[1]
    )

    assert result.unread_pages == (1,)


async def test_page_outside_the_document_is_reported_not_substituted(
    settings: Settings, tesseract: FakeTesseract
) -> None:
    result = await TesseractOcrEngine(ocr_settings(settings)).recognize_pages(
        make_pdf(2), page_numbers=[1, 7]
    )

    assert sorted(result.text_by_page) == [1]
    assert result.unread_pages == (7,)
    assert len(tesseract.commands) == 1


async def test_unparseable_bytes_yield_unread_pages_not_an_exception(
    settings: Settings, tesseract: FakeTesseract
) -> None:
    result = await TesseractOcrEngine(ocr_settings(settings)).recognize_pages(
        b"%PDF-1.7 truncated", page_numbers=[1, 2]
    )

    assert dict(result.text_by_page) == {}
    assert result.unread_pages == (1, 2)


# --- Real binary ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract is not installed")
async def test_real_tesseract_reads_a_scanned_page(settings: Settings) -> None:
    """End-to-end against the demo tender, flattened to an image so OCR is the only way in."""
    source = pymupdf.open(SAMPLE_TENDER)
    scanned = pymupdf.open()
    page = scanned.new_page(width=source[0].rect.width, height=source[0].rect.height)
    page.insert_image(page.rect, pixmap=source[0].get_pixmap(dpi=200))
    content = bytes(scanned.tobytes())
    scanned.close()
    source.close()

    native = pymupdf.open(stream=content, filetype="pdf")
    assert needs_ocr(native[0].get_text("text"), min_chars=40) is True
    native.close()

    engine = build_ocr_engine(ocr_settings(settings))
    assert engine.available is True

    result = await engine.recognize_pages(content, page_numbers=[1])

    assert result.pages_without_text == ()
    assert "INVITATION TO TENDER" in result.text_by_page[1]
