"""Upload validation: extension, magic bytes, size, and hashing.

The client's Content-Type header and filename are both attacker-controlled, so acceptance is
decided by the file's own leading bytes. A `.exe` renamed to `.pdf` fails the sniff; a PDF
posted with a wrong Content-Type still passes. Full structural parsing (page count, text) is
Phase 4's job — this layer only guarantees "plausibly a PDF, within limits, hashed".
"""

from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass

from app.api.errors import AppError

#: %PDF- — every PDF starts with this, per the specification.
PDF_MAGIC = b"%PDF-"

ALLOWED_EXTENSIONS = (".pdf",)
PDF_MIME_TYPE = "application/pdf"

MAX_FILENAME_LENGTH = 255


class UploadValidationError(AppError):
    status = 422
    code = "UPLOAD_INVALID"
    title = "Upload rejected"
    slug = "upload-invalid"


class UploadTooLargeError(AppError):
    status = 413
    code = "UPLOAD_TOO_LARGE"
    title = "Upload too large"
    slug = "upload-too-large"


@dataclass(frozen=True, slots=True)
class ValidatedUpload:
    content: bytes
    sha256: str
    size_bytes: int
    safe_original_filename: str


def sanitize_filename(raw: str | None) -> str:
    """A display-safe rendering of the client's filename.

    Used only for display and export. Storage paths are generated server-side, so this function
    is presentation hygiene, not a security boundary.
    """
    if not raw:
        return "document.pdf"
    # Strip any path the client sent ("C:\docs\tender.pdf", "../../etc/passwd").
    name = raw.replace("\\", "/").rsplit("/", 1)[-1]
    # Remove control characters; normalize to a consistent form.
    name = unicodedata.normalize("NFKC", name)
    name = "".join(ch for ch in name if ch.isprintable() and ch not in '<>:"|?*')
    name = name.strip(". ")
    if not name:
        return "document.pdf"
    return name[:MAX_FILENAME_LENGTH]


def validate_pdf_upload(
    *,
    content: bytes,
    original_filename: str | None,
    max_bytes: int,
) -> ValidatedUpload:
    """Accept or reject an uploaded file. Raises an AppError subclass with a clear detail."""
    safe_name = sanitize_filename(original_filename)

    if not safe_name.lower().endswith(ALLOWED_EXTENSIONS):
        raise UploadValidationError("Only PDF files are accepted. The filename must end in .pdf.")

    if len(content) == 0:
        raise UploadValidationError("The uploaded file is empty.")

    if len(content) > max_bytes:
        raise UploadTooLargeError(
            f"The file is {len(content):,} bytes; the maximum accepted size is {max_bytes:,} bytes."
        )

    if not content.startswith(PDF_MAGIC):
        # The filename claimed .pdf but the bytes disagree. The bytes win.
        raise UploadValidationError(
            "The file does not appear to be a PDF. Its content does not match the PDF format."
        )

    return ValidatedUpload(
        content=content,
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        safe_original_filename=safe_name,
    )
