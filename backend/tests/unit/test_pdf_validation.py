"""Upload validation: the bytes decide, not the filename or the client's Content-Type."""

from __future__ import annotations

import pytest

from app.documents.validation import (
    UploadTooLargeError,
    UploadValidationError,
    sanitize_filename,
    validate_pdf_upload,
)

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\ntrailer\n%%EOF"
MAX = 1024 * 1024


def test_valid_pdf_is_accepted_and_hashed() -> None:
    result = validate_pdf_upload(content=PDF, original_filename="tender.pdf", max_bytes=MAX)
    assert result.size_bytes == len(PDF)
    assert len(result.sha256) == 64
    assert result.safe_original_filename == "tender.pdf"


def test_non_pdf_bytes_with_pdf_name_are_rejected() -> None:
    """An executable renamed to .pdf must fail on its content."""
    with pytest.raises(UploadValidationError, match="does not appear to be a PDF"):
        validate_pdf_upload(
            content=b"MZ\x90\x00executable bytes", original_filename="invoice.pdf", max_bytes=MAX
        )


def test_wrong_extension_is_rejected_even_with_pdf_bytes() -> None:
    with pytest.raises(UploadValidationError, match=r"must end in \.pdf"):
        validate_pdf_upload(content=PDF, original_filename="tender.docx", max_bytes=MAX)


def test_empty_file_is_rejected() -> None:
    with pytest.raises(UploadValidationError, match="empty"):
        validate_pdf_upload(content=b"", original_filename="tender.pdf", max_bytes=MAX)


def test_oversized_file_is_rejected_with_413() -> None:
    with pytest.raises(UploadTooLargeError) as exc_info:
        validate_pdf_upload(content=PDF, original_filename="tender.pdf", max_bytes=10)
    assert exc_info.value.status == 413


def test_identical_content_hashes_identically() -> None:
    a = validate_pdf_upload(content=PDF, original_filename="a.pdf", max_bytes=MAX)
    b = validate_pdf_upload(content=PDF, original_filename="b.pdf", max_bytes=MAX)
    assert a.sha256 == b.sha256


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../etc/passwd.pdf", "passwd.pdf"),
        ("C:\\docs\\..\\tender.pdf", "tender.pdf"),
        ("  spaced name.pdf  ", "spaced name.pdf"),
        ("evil<script>.pdf", "evilscript.pdf"),
        (None, "document.pdf"),
        ("", "document.pdf"),
        ("...", "document.pdf"),
    ],
)
def test_filename_sanitization(raw: str | None, expected: str) -> None:
    assert sanitize_filename(raw) == expected


def test_overlong_filename_is_truncated() -> None:
    assert len(sanitize_filename("x" * 500 + ".pdf")) <= 255
