"""Register lookups for the certificate check in screening.

`certificate_registry` is reference data, not user data. No row belongs to an account, nothing
is written through the API, and the whole table is the public part of somebody else's register
reproduced locally (`app/models/certificate.py`). So this extends `BaseRepository` rather than
`OwnedRepository`: there is no owner to scope by, and an unscoped read here cannot leak a
user's data because the table contains none.

**Normalisation happens here, not at the call site.** `certificate_number` stores the folded
key that `app.domain.certificates.normalize_certificate_number` produces, so a query built from
a raw printed number would silently match nothing — the worst possible failure for a check whose
whole job is to distinguish "not registered" from "registered". Both methods therefore fold
their arguments before querying. Folding is idempotent, so a caller that already normalised
(everything coming out of `extract_certificate_numbers` has) loses nothing by passing the key
straight through.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select

from app.domain.certificates import RegisteredCertificate, normalize_certificate_number
from app.models.certificate import CertificateRecord
from app.repositories.base import BaseRepository


def to_domain(record: CertificateRecord) -> RegisteredCertificate:
    """Convert a register row into the value object the domain layer assesses.

    The conversion lives beside the query so no caller is tempted to hand an ORM row to
    `app.domain.certificates`, which is pure by design and must stay loadable without a
    database. `scope` and the issue date are deliberately dropped: assessment does not read
    them, and a value object carrying fields nobody uses invites somebody to start using them
    outside a session.
    """
    return RegisteredCertificate(
        number=record.certificate_number,
        display_number=record.display_number,
        standard=record.standard,
        issued_to=record.issued_to,
        issuing_body=record.issuing_body,
        status=record.status,
        expires_on=record.expires_on,
    )


class CertificateRepository(BaseRepository[CertificateRecord]):
    """Read-only access to the accreditation register. Screening's only query into it."""

    model = CertificateRecord

    async def get_by_number(self, number: str) -> CertificateRecord | None:
        """Look up one certificate. `None` means the register does not list it.

        `scalar_one_or_none` rather than `.first()`: `certificate_number` is unique, so a second
        row means that constraint failed and the error is what we want to see.
        """
        key = normalize_certificate_number(number)
        if not key:
            # Nothing but punctuation. The query would match nothing anyway; returning early
            # keeps a garbage read out of the register's access log.
            return None
        result = await self.session.execute(
            select(CertificateRecord).where(CertificateRecord.certificate_number == key)
        )
        return result.scalar_one_or_none()

    async def get_many_by_numbers(self, numbers: Sequence[str]) -> dict[str, CertificateRecord]:
        """Look up a whole submission's certificates in one statement.

        One query rather than one per candidate: a submission can carry a certificate for every
        checklist entry that names one, and screening runs in a worker holding a transaction
        open across the whole run. Keyed by the normalised number so the caller can index the
        result with the same key it searched for; a number the register does not list is simply
        absent, which is exactly what `assess_certificate` reads as "not in register".
        """
        keys = {normalize_certificate_number(number) for number in numbers}
        keys.discard("")
        if not keys:
            return {}
        result = await self.session.execute(
            select(CertificateRecord).where(CertificateRecord.certificate_number.in_(keys))
        )
        return {record.certificate_number: record for record in result.scalars()}
