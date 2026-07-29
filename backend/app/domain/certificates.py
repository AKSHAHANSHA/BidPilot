"""Reading a certificate number out of a document, and deciding what it is worth.

Two pure pieces, no ORM and no I/O, so both are testable without a database:

* `extract_certificate_numbers` finds candidate numbers in extracted page text.
* `assess_certificate` turns a register lookup into a screening verdict.

The rule this module exists to enforce: a certificate is worth what its register says, not
what the PDF says. Anyone can type a number onto a page. Screening therefore credits a
certificate only when the number is present in the register and currently valid, and reports
every other case in terms a vendor can act on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum

from app.domain.enums import CertificateStatus, DocumentScreeningVerdict

#: The canonical shape: `ISO-9001-AE-04821`. Deliberately tolerant about separators and case,
#: because the number is being read out of extracted PDF text where a hyphen may have arrived
#: as an en dash, a space, or nothing at all. It is NOT tolerant about the structure: matching
#: a bare five-digit run would pick up invoice numbers, phone extensions and page footers.
_CERTIFICATE_PATTERN = re.compile(
    r"""
    \bISO            # the literal prefix
    [\s\-\u2010-\u2015_.]{0,2}
    (?P<standard>\d{4,5})          # 9001, 14001, 45001, 27001 ...
    [\s\-\u2010-\u2015_.]{0,2}
    (?P<country>[A-Z]{2})          # issuing country, e.g. AE
    [\s\-\u2010-\u2015_.]{0,2}
    (?P<serial>\d{4,6})\b          # the serial
    """,
    re.IGNORECASE | re.VERBOSE,
)

#: Anything that is not a letter or a digit is noise for lookup purposes.
_NOISE = re.compile(r"[^A-Z0-9]")

#: Bounds how many candidates one page can contribute. A page that appears to hold fifty
#: certificate numbers is a table of contents or an attack, not a certificate.
MAX_CANDIDATES_PER_DOCUMENT = 20


def normalize_certificate_number(raw: str) -> str:
    """Fold a printed number to its lookup key.

    Both the register and the extracted candidate go through this, so `ISO 9001 AE 04821`,
    `iso-9001-ae-04821` and `ISO9001AE04821` are the same key. Storing the key rather than
    normalising at query time keeps the unique index meaningful.
    """
    return _NOISE.sub("", raw.upper())


@dataclass(frozen=True, slots=True)
class CertificateCandidate:
    """A number found in a document, with where it was found."""

    #: The lookup key.
    number: str
    #: Exactly as it appeared, for quoting back to the reader.
    raw: str
    standard: str
    page: int


def extract_certificate_numbers(
    text_by_page: dict[int, str], *, limit: int = MAX_CANDIDATES_PER_DOCUMENT
) -> tuple[CertificateCandidate, ...]:
    """Find certificate numbers in extracted page text, in page order.

    Duplicates are collapsed on the *first* page they appear, because a certificate number
    repeated in a footer should cite the page that actually carries the certificate.
    """
    found: dict[str, CertificateCandidate] = {}

    for page in sorted(text_by_page):
        for match in _CERTIFICATE_PATTERN.finditer(text_by_page[page] or ""):
            raw = match.group(0)
            key = normalize_certificate_number(raw)
            if key in found:
                continue
            found[key] = CertificateCandidate(
                number=key,
                raw=raw.strip(),
                standard=f"ISO {match.group('standard')}",
                page=page,
            )
            if len(found) >= limit:
                return tuple(found.values())

    return tuple(found.values())


class CertificateOutcome(StrEnum):
    """Why a certificate was or was not credited. Drives the message the vendor reads."""

    VERIFIED = "verified"
    NOT_IN_REGISTER = "not_in_register"
    EXPIRED = "expired"
    SUSPENDED = "suspended"
    WITHDRAWN = "withdrawn"
    NO_NUMBER_FOUND = "no_number_found"


@dataclass(frozen=True, slots=True)
class RegisteredCertificate:
    """The register's answer, as the domain needs it.

    A plain value object rather than the ORM row, so this module stays free of SQLAlchemy and
    can be exercised with a literal in a unit test.
    """

    number: str
    display_number: str
    standard: str
    issued_to: str
    issuing_body: str
    status: str
    expires_on: date | None


@dataclass(frozen=True, slots=True)
class CertificateAssessment:
    """What screening concluded about one uploaded certificate."""

    outcome: CertificateOutcome
    verdict: DocumentScreeningVerdict
    #: Reader-facing sentence. States what was checked, never that the vendor lacks anything.
    explanation: str
    candidate: CertificateCandidate | None = None
    record: RegisteredCertificate | None = None

    @property
    def is_credited(self) -> bool:
        return self.outcome is CertificateOutcome.VERIFIED


def assess_certificate(
    candidate: CertificateCandidate | None,
    record: RegisteredCertificate | None,
    *,
    today: date | None = None,
) -> CertificateAssessment:
    """Decide the verdict for one certificate.

    Pure: the caller does the register lookup and hands the result in. `record` is `None` when
    the number was not found, which is the case this whole feature exists to catch.
    """
    now = today or datetime.now(tz=UTC).date()

    if candidate is None:
        return CertificateAssessment(
            outcome=CertificateOutcome.NO_NUMBER_FOUND,
            # Not `MISSING`: a file was supplied. The problem is that no certificate number
            # could be read out of it, which is a different thing to fix.
            verdict=DocumentScreeningVerdict.PRESENT_UNVERIFIED,
            explanation=(
                "A certificate was supplied but no certificate number could be read from it, "
                "so it could not be checked against the issuing register. If the number is "
                "printed on a scanned page, upload a clearer copy."
            ),
        )

    if record is None:
        return CertificateAssessment(
            outcome=CertificateOutcome.NOT_IN_REGISTER,
            verdict=DocumentScreeningVerdict.PRESENT_UNVERIFIED,
            explanation=(
                f"Certificate number {candidate.raw} was read from page {candidate.page} but "
                "does not appear in the accreditation register held by this portal. It earns "
                "no credit until it can be confirmed. If the certificate is genuine, the "
                "register may simply not list it — raise a clarification with the buyer."
            ),
            candidate=candidate,
        )

    if record.status == CertificateStatus.WITHDRAWN.value:
        return CertificateAssessment(
            outcome=CertificateOutcome.WITHDRAWN,
            verdict=DocumentScreeningVerdict.PRESENT_UNVERIFIED,
            explanation=(
                f"Certificate {record.display_number} is recorded as withdrawn by "
                f"{record.issuing_body}, so it cannot be credited."
            ),
            candidate=candidate,
            record=record,
        )

    if record.status == CertificateStatus.SUSPENDED.value:
        return CertificateAssessment(
            outcome=CertificateOutcome.SUSPENDED,
            verdict=DocumentScreeningVerdict.PRESENT_UNVERIFIED,
            explanation=(
                f"Certificate {record.display_number} is recorded as suspended by "
                f"{record.issuing_body}. It cannot be credited while the suspension stands."
            ),
            candidate=candidate,
            record=record,
        )

    # The date decides, not the stored status: a register refreshed on a schedule always holds
    # rows whose status has not caught up with their expiry.
    if record.expires_on is not None and record.expires_on < now:
        return CertificateAssessment(
            outcome=CertificateOutcome.EXPIRED,
            # Half credit, in line with every other expired document: it was genuinely issued,
            # and the fix is a renewal rather than a new claim.
            verdict=DocumentScreeningVerdict.PRESENT_EXPIRED,
            explanation=(
                f"Certificate {record.display_number} is in the register but expired on "
                f"{record.expires_on.isoformat()}. Upload the renewed certificate."
            ),
            candidate=candidate,
            record=record,
        )

    return CertificateAssessment(
        outcome=CertificateOutcome.VERIFIED,
        verdict=DocumentScreeningVerdict.PRESENT,
        explanation=(
            f"Certificate {record.display_number} ({record.standard}) was confirmed against "
            f"the register, issued to {record.issued_to} by {record.issuing_body}"
            + (f" and valid to {record.expires_on.isoformat()}." if record.expires_on else ".")
        ),
        candidate=candidate,
        record=record,
    )
