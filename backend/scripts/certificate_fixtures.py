"""The accreditation register the demo screens certificates against.

Generated rather than hand-listed: a hundred rows of near-identical reference data is exactly
the kind of thing that should be produced by a loop with a fixed seed. Deterministic, so the
same numbers exist after every reseed and a demo script written today still works tomorrow.

Every issuing body here is invented. Nothing in this file corresponds to a real accreditation
body or a real certificate.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta

from app.domain.certificates import normalize_certificate_number
from app.domain.enums import CertificateStatus

#: Standards a UAE contractor plausibly holds, with the scope wording that goes with each.
STANDARDS: tuple[tuple[str, str, str], ...] = (
    ("9001", "ISO 9001", "Quality management systems"),
    ("14001", "ISO 14001", "Environmental management systems"),
    ("45001", "ISO 45001", "Occupational health and safety management"),
    ("27001", "ISO 27001", "Information security management"),
    ("22301", "ISO 22301", "Business continuity management"),
    ("50001", "ISO 50001", "Energy management systems"),
)

#: Invented certification bodies.
ISSUING_BODIES: tuple[str, ...] = (
    "Emirates International Accreditation Centre",
    "Gulf Certification Bureau",
    "Arabian Peninsula Quality Registrar",
    "Levant & Gulf Assurance Services",
    "Northern Emirates Certification Council",
)

#: Invented third-party holders, so the register is plainly wider than the demo's own vendors.
THIRD_PARTY_HOLDERS: tuple[str, ...] = (
    "Al Rabee Contracting LLC",
    "Sahara Marine Engineering",
    "Khaleej Technical Services",
    "Oryx Industrial Maintenance",
    "Bab Al Bahr Trading Co",
    "Dune Logistics Group",
    "Silver Coast Electrical",
    "Palm Grove Landscaping LLC",
    "Anwar Medical Supplies",
    "Rasha Facilities Services",
    "Nakheel Steel Fabricators",
    "Zayed Road Civil Works",
    "Blue Horizon Consultancy",
    "Fajr Security Solutions",
    "Marsa Catering Services",
)

#: How many rows to generate. The user asked for at least a hundred; this leaves headroom so a
#: vendor's certificate is not always the one immediately after another vendor's.
REGISTRY_SIZE = 120

#: A handful of numbers that deliberately do NOT exist in the register, for demonstrating the
#: rejection path. Shaped exactly like a real one, which is the point — the format proves
#: nothing, only the lookup does.
UNREGISTERED_NUMBERS: tuple[str, ...] = (
    "ISO-9001-AE-99001",
    "ISO-14001-AE-99002",
    "ISO-45001-AE-99003",
    "ISO-27001-AE-99004",
)


@dataclass(frozen=True, slots=True)
class CertificateFixture:
    """One register row, ready to persist."""

    certificate_number: str
    display_number: str
    standard: str
    issued_to: str
    issuing_body: str
    scope: str
    issued_on: date
    expires_on: date
    status: str


def _display(standard_code: str, serial: int) -> str:
    return f"ISO-{standard_code}-AE-{serial:05d}"


def build_registry(
    vendor_names: tuple[str, ...],
    *,
    today: date,
    rng: random.Random,
) -> tuple[CertificateFixture, ...]:
    """Generate the register.

    The first rows are assigned to the demo's own vendors so their submissions verify; the rest
    belong to invented third parties. Statuses are spread so the demo can show every branch of
    `assess_certificate`: mostly active, a few expired, a couple suspended, a couple withdrawn.
    """
    fixtures: list[CertificateFixture] = []
    serial = 4800  # arbitrary, stable starting point so numbers look issued rather than seeded

    # Every vendor gets a full set, so whichever tender they apply to their certificate is on
    # file. Without this the "verified" path would be luck of the draw.
    holders: list[str] = []
    for name in vendor_names:
        holders.extend([name] * len(STANDARDS))
    while len(holders) < REGISTRY_SIZE:
        holders.append(THIRD_PARTY_HOLDERS[len(holders) % len(THIRD_PARTY_HOLDERS)])

    for index, holder in enumerate(holders[:REGISTRY_SIZE]):
        standard_code, standard_label, scope = STANDARDS[index % len(STANDARDS)]
        serial += rng.randrange(3, 29)
        display = _display(standard_code, serial)

        # Vendor certificates are always active and in date: they are the control group the
        # "verified" demo path depends on. Third-party rows carry the interesting states.
        is_vendor = holder in vendor_names
        if is_vendor:
            status = CertificateStatus.ACTIVE.value
            issued_on = today - timedelta(days=rng.randrange(200, 900))
            expires_on = today + timedelta(days=rng.randrange(180, 1000))
        else:
            roll = rng.random()
            if roll < 0.08:
                status = CertificateStatus.EXPIRED.value
                issued_on = today - timedelta(days=rng.randrange(1200, 2000))
                expires_on = today - timedelta(days=rng.randrange(20, 300))
            elif roll < 0.11:
                status = CertificateStatus.SUSPENDED.value
                issued_on = today - timedelta(days=rng.randrange(300, 900))
                expires_on = today + timedelta(days=rng.randrange(60, 600))
            elif roll < 0.14:
                status = CertificateStatus.WITHDRAWN.value
                issued_on = today - timedelta(days=rng.randrange(400, 1200))
                expires_on = today + timedelta(days=rng.randrange(30, 500))
            else:
                status = CertificateStatus.ACTIVE.value
                issued_on = today - timedelta(days=rng.randrange(100, 1000))
                expires_on = today + timedelta(days=rng.randrange(120, 1100))

        fixtures.append(
            CertificateFixture(
                certificate_number=normalize_certificate_number(display),
                display_number=display,
                standard=standard_label,
                issued_to=holder,
                issuing_body=ISSUING_BODIES[index % len(ISSUING_BODIES)],
                scope=scope,
                issued_on=issued_on,
                expires_on=expires_on,
                status=status,
            )
        )

    return tuple(fixtures)
