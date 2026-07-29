"""Seed the marketplace over a slow link, in bulk.

`seed_portal.py` drives everything through `ListingService` so the demo obeys the same
validators as live traffic. That is the right default, and against localhost it costs about
thirty seconds. Against a hosted database it is unusable: it issues thousands of statements and
each one pays the round-trip, so a full seed does not finish inside a coffee break.

This script produces the same marketplace with roughly two orders of magnitude fewer
round-trips: objects are built in memory and flushed in a handful of `add_all` batches. The
trade-off is explicit — it bypasses the service layer, so it can in principle write a row the
API would have refused. It stays honest where it matters:

* the score comes from `calculate_screening_score`, the real scorer;
* the ISO verdict comes from `assess_certificate`, the real register check;
* every constraint in the schema still applies, because the database still enforces it.

No PDFs are written. On a serverless deployment the filesystem is discarded between requests,
so a stored bundle would be unreadable by the time anyone asked for it; the document rows exist
so findings can cite them, and the citation text lives in the finding itself.

    python scripts/seed_portal_fast.py
"""

from __future__ import annotations

import asyncio
import hashlib
import random
import sys
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import delete  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import create_engine  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.domain.certificates import (  # noqa: E402
    CertificateCandidate,
    RegisteredCertificate,
    assess_certificate,
    normalize_certificate_number,
)
from app.domain.enums import (  # noqa: E402
    AccountType,
    ApplicationStatus,
    DocumentExtractionStatus,
    DocumentScreeningVerdict,
    ListingStatus,
    NotificationType,
    RequiredDocumentType,
    ScreeningStatus,
    TenderCategory,
)
from app.domain.screening import (  # noqa: E402
    RequirementVerdict,
    ScreeningRequirement,
    calculate_screening_score,
)
from app.models.application import Application, ApplicationDocument  # noqa: E402
from app.models.certificate import CertificateRecord  # noqa: E402
from app.models.listing import ListingDocumentRequirement, TenderListing  # noqa: E402
from app.models.notification import Notification  # noqa: E402
from app.models.organisation import Organisation  # noqa: E402
from app.models.screening import ApplicationScreening, ScreeningFinding  # noqa: E402
from app.models.user import User  # noqa: E402
from scripts.certificate_fixtures import UNREGISTERED_NUMBERS, build_registry  # noqa: E402
from scripts.portal_fixtures import (  # noqa: E402
    BASE_MANDATORY,
    BASE_OPTIONAL,
    BUYERS,
    CATEGORY_REQUIREMENTS,
    TEMPLATES,
    VENDORS,
)
from scripts.seed_portal import (  # noqa: E402
    DEMO_EMAIL_DOMAIN,
    DEMO_PASSWORD,
    LISTING_VARIANTS,
    MIN_LISTINGS_PER_CATEGORY,
    RANDOM_SEED,
    _email_for,
    _slug,
)

#: Every id is assigned at construction rather than left to the column default, which does
#: not fire until flush. The whole object graph is built in memory before anything is sent,
#: so a child referencing `parent.id` would otherwise capture None.

#: Applications to create. Enough for the dashboard charts and the certificate demo to be
#: meaningful without multiplying the row count by the number of listings.
APPLICATIONS_PER_VENDOR = 8


def _requirement_rows(
    listing_id: uuid.UUID, category: TenderCategory
) -> list[ListingDocumentRequirement]:
    seen: set[str] = set()
    rows: list[ListingDocumentRequirement] = []

    def add(document_type: RequiredDocumentType, *, mandatory: bool, weight: int) -> None:
        if document_type.value in seen:
            return
        seen.add(document_type.value)
        rows.append(
            ListingDocumentRequirement(
                listing_id=listing_id,
                document_type=document_type.value,
                is_mandatory=mandatory,
                weight=weight,
                display_order=len(rows),
            )
        )

    for document_type in BASE_MANDATORY:
        add(document_type, mandatory=True, weight=3)
    for document_type, mandatory in CATEGORY_REQUIREMENTS.get(category, ()):
        add(document_type, mandatory=mandatory, weight=5 if mandatory else 2)
    for document_type in BASE_OPTIONAL:
        add(document_type, mandatory=False, weight=1)
    return rows


async def _wipe(session: AsyncSession) -> None:
    """Clear demo rows with set-based deletes rather than ORM cascade.

    The ORM path loads every child and issues a delete per row, which is exactly the round-trip
    storm this script exists to avoid. Foreign keys still cascade in the database, so deleting
    the users is enough — it just has to be one statement.
    """
    await session.execute(delete(CertificateRecord))
    await session.execute(delete(User).where(User.email.like(f"%@{DEMO_EMAIL_DOMAIN}")))
    await session.commit()


async def main() -> int:
    settings = get_settings()
    configure_logging(level=settings.log_level_number, json_output=False)
    engine = create_engine(settings)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    rng = random.Random(RANDOM_SEED)  # noqa: S311 - demo spread, not security
    now = datetime.now(tz=UTC)
    today = now.date()

    try:
        async with factory() as session:
            await _wipe(session)

            # --- accounts -------------------------------------------------------------
            users: list[User] = []
            organisations: list[Organisation] = []
            buyer_pairs: list[tuple[User, Organisation]] = []
            vendor_pairs: list[tuple[User, Organisation]] = []

            def account(spec: dict[str, object], account_type: AccountType) -> None:
                name = str(spec["name"])
                user = User(
                    id=uuid.uuid4(),
                    email=_email_for(name),
                    password_hash=hash_password(DEMO_PASSWORD),
                    display_name=f"{name} — demo account",
                    account_type=account_type.value,
                )
                organisation = Organisation(
                    id=uuid.uuid4(),
                    owner_user_id=user.id,
                    account_type=account_type.value,
                    name=name,
                    description=str(spec["description"]),
                    emirate=str(spec["emirate"]),
                    city=str(spec["city"]),
                    industry=str(spec["industry"]),
                    contact_email=f"contact@{_slug(name)}.example",
                    employee_count=spec.get("employee_count"),  # type: ignore[arg-type]
                    year_established=spec.get("year_established"),  # type: ignore[arg-type]
                    is_verified=account_type is AccountType.COMPANY,
                )
                users.append(user)
                organisations.append(organisation)
                (buyer_pairs if account_type is AccountType.COMPANY else vendor_pairs).append(
                    (user, organisation)
                )

            for spec in BUYERS:
                account(spec, AccountType.COMPANY)
            for spec in VENDORS:
                account(spec, AccountType.VENDOR)

            # Users before organisations: the foreign key is checked at flush, not at commit.
            session.add_all(users)
            await session.flush()
            session.add_all(organisations)
            await session.flush()

            # --- certificate register --------------------------------------------------
            vendor_names = tuple(org.name for _, org in vendor_pairs)
            fixtures = build_registry(vendor_names, today=today, rng=rng)
            session.add_all(
                CertificateRecord(
                    certificate_number=f.certificate_number,
                    display_number=f.display_number,
                    standard=f.standard,
                    issued_to=f.issued_to,
                    issuing_body=f.issuing_body,
                    scope=f.scope,
                    issued_on=f.issued_on,
                    expires_on=f.expires_on,
                    status=f.status,
                )
                for f in fixtures
            )
            await session.commit()

            registry = {f.certificate_number: f for f in fixtures}
            by_holder: dict[str, list[str]] = {}
            for f in fixtures:
                by_holder.setdefault(f.issued_to, []).append(f.display_number)

            # --- listings ---------------------------------------------------------------
            listings: list[TenderListing] = []
            requirements: list[ListingDocumentRequirement] = []
            sequence = 0

            for user, organisation in buyer_pairs:
                for category in BUYERS[buyer_pairs.index((user, organisation))]["categories"]:  # type: ignore[index]
                    templates = list(TEMPLATES.get(category, ()))
                    if not templates:
                        continue
                    plan = [(t, "", 1.0) for t in templates]
                    variant = 1
                    while len(plan) < MIN_LISTINGS_PER_CATEGORY and variant < len(LISTING_VARIANTS):
                        suffix, multiplier = LISTING_VARIANTS[variant]
                        plan.append((templates[(variant - 1) % len(templates)], suffix, multiplier))
                        variant += 1

                    for template, suffix, scale in plan:
                        sequence += 1
                        deadline = (now + timedelta(days=5 + (sequence * 7) % 88)).replace(
                            hour=13, minute=0, second=0, microsecond=0
                        )
                        low, high = template.budget
                        listing = TenderListing(
                            id=uuid.uuid4(),
                            owner_user_id=user.id,
                            organisation_id=organisation.id,
                            title=f"{template.title} {suffix}".strip(),
                            summary=template.summary,
                            description=template.description,
                            reference=f"{_slug(organisation.name)[:6].upper()}-2026-{sequence:03d}",
                            category=category.value,
                            industry=organisation.industry,
                            tags=list(template.tags),
                            emirate=organisation.emirate,
                            city=organisation.city,
                            budget_min=Decimal(int(low * scale)),
                            budget_max=Decimal(int(high * scale)),
                            submission_deadline=deadline,
                            questions_deadline=deadline - timedelta(days=10),
                            published_at=now - timedelta(days=rng.randrange(1, 30)),
                            contract_duration_months=template.duration_months,
                            min_years_experience=template.min_years_experience,
                            requires_bid_bond=template.requires_bid_bond,
                            bid_bond_percentage=(
                                Decimal("2.00") if template.requires_bid_bond else None
                            ),
                            status=ListingStatus.PUBLISHED.value,
                        )
                        listings.append(listing)
                        requirements.extend(_requirement_rows(listing.id, category))

            session.add_all(listings)
            await session.flush()
            session.add_all(requirements)
            await session.commit()

            by_listing: dict[uuid.UUID, list[ListingDocumentRequirement]] = {}
            for row in requirements:
                by_listing.setdefault(row.listing_id, []).append(row)

            # --- applications, screenings, findings ------------------------------------
            applications: list[Application] = []
            documents: list[ApplicationDocument] = []
            screenings: list[ApplicationScreening] = []
            findings: list[ScreeningFinding] = []
            notifications: list[Notification] = []
            created = 0
            iso_seen = 0

            for vendor_user, vendor_org in vendor_pairs:
                pool = list(listings)
                rng.shuffle(pool)
                for listing in pool[:APPLICATIONS_PER_VENDOR]:
                    checklist = by_listing.get(listing.id, [])
                    if not checklist:
                        continue

                    wants_iso = any(
                        r.document_type == RequiredDocumentType.ISO_CERTIFICATION.value
                        for r in checklist
                    )
                    assessment = None
                    if wants_iso:
                        owned = by_holder.get(vendor_org.name, [])
                        # Deterministic, not sampled: every third certificate-bearing bid
                        # prints an unregistered number. A demo of the register check that
                        # depends on a dice roll can come up empty, which is exactly what
                        # happened the first time this ran.
                        iso_seen += 1
                        if iso_seen % 3 == 0 or not owned:
                            printed = UNREGISTERED_NUMBERS[iso_seen % len(UNREGISTERED_NUMBERS)]
                        else:
                            printed = owned[iso_seen % len(owned)]
                        found = registry.get(normalize_certificate_number(printed))
                        assessment = assess_certificate(
                            CertificateCandidate(
                                number=normalize_certificate_number(printed),
                                raw=printed,
                                standard="ISO 9001",
                                page=1,
                            ),
                            None
                            if found is None
                            else RegisteredCertificate(
                                number=found.certificate_number,
                                display_number=found.display_number,
                                standard=found.standard,
                                issued_to=found.issued_to,
                                issuing_body=found.issuing_body,
                                status=found.status,
                                expires_on=found.expires_on,
                            ),
                        )

                    verdicts: list[RequirementVerdict] = []
                    for index, row in enumerate(checklist):
                        document_type = RequiredDocumentType(row.document_type)
                        if document_type is RequiredDocumentType.ISO_CERTIFICATION and assessment:
                            verdict = assessment.verdict
                        elif index < 3 or rng.random() < 0.78:
                            verdict = DocumentScreeningVerdict.PRESENT
                        elif rng.random() < 0.4:
                            verdict = DocumentScreeningVerdict.PRESENT_EXPIRED
                        else:
                            verdict = DocumentScreeningVerdict.MISSING
                        verdicts.append(
                            RequirementVerdict(
                                requirement=ScreeningRequirement(
                                    document_type=document_type,
                                    is_mandatory=row.is_mandatory,
                                    weight=row.weight,
                                ),
                                verdict=verdict,
                            )
                        )

                    result = calculate_screening_score(verdicts)
                    budget = listing.budget_max or listing.budget_min or Decimal(1_000_000)
                    bid = (budget * Decimal(rng.randrange(82, 99))) / Decimal(100)
                    cost = (bid * Decimal(rng.randrange(72, 93))) / Decimal(100)
                    submitted_at = now - timedelta(days=rng.randrange(3, 60))

                    roll = rng.random()
                    if result.has_blocking_gap:
                        status, decided = (
                            (ApplicationStatus.REJECTED, submitted_at + timedelta(days=6))
                            if roll < 0.5
                            else (ApplicationStatus.UNDER_REVIEW, None)
                        )
                    elif roll < 0.3:
                        status, decided = (
                            ApplicationStatus.APPROVED,
                            submitted_at + timedelta(days=8),
                        )
                    elif roll < 0.45:
                        status, decided = (
                            ApplicationStatus.REJECTED,
                            submitted_at + timedelta(days=8),
                        )
                    elif roll < 0.7:
                        status, decided = ApplicationStatus.SHORTLISTED, None
                    else:
                        status, decided = ApplicationStatus.UNDER_REVIEW, None

                    application = Application(
                        id=uuid.uuid4(),
                        listing_id=listing.id,
                        vendor_user_id=vendor_user.id,
                        vendor_organisation_id=vendor_org.id,
                        status=status.value,
                        cover_letter=(
                            f"{vendor_org.name} is pleased to submit a proposal for "
                            f"{listing.title}. Our team has delivered comparable work across "
                            "the UAE and can mobilise within four weeks of award."
                        ),
                        bid_amount=bid.quantize(Decimal("0.01")),
                        estimated_cost=cost.quantize(Decimal("0.01")),
                        proposed_duration_months=listing.contract_duration_months,
                        submitted_at=submitted_at,
                        decided_at=decided,
                        first_viewed_at=submitted_at + timedelta(days=1),
                        decision_note=(
                            "Strongest technical response with a credible programme."
                            if status is ApplicationStatus.APPROVED
                            else "Another bidder scored higher on technical capability."
                            if status is ApplicationStatus.REJECTED
                            else None
                        ),
                    )
                    applications.append(application)

                    bundle = ApplicationDocument(
                        id=uuid.uuid4(),
                        application_id=application.id,
                        vendor_user_id=vendor_user.id,
                        original_filename="submission-bundle.pdf",
                        stored_filename=f"{uuid.uuid4().hex}.pdf",
                        storage_key=(
                            f"{vendor_user.id}/applications/{application.id}/{uuid.uuid4().hex}.pdf"
                        ),
                        mime_type="application/pdf",
                        size_bytes=48_000,
                        sha256=hashlib.sha256(str(application.id).encode()).hexdigest(),
                        page_count=len(checklist),
                        extraction_status=DocumentExtractionStatus.EXTRACTED.value,
                    )
                    documents.append(bundle)

                    screening = ApplicationScreening(
                        id=uuid.uuid4(),
                        application_id=application.id,
                        status=ScreeningStatus.COMPLETED.value,
                        overall_score=result.score,
                        mandatory_met=result.mandatory_met,
                        mandatory_total=result.mandatory_total,
                        optional_met=result.optional_met,
                        optional_total=result.optional_total,
                        documents_processed=1,
                        pages_extracted=len(checklist),
                        pages_needing_ocr=0,
                        summary=(
                            f"{vendor_org.name} supplied {result.mandatory_met} of "
                            f"{result.mandatory_total} mandatory documents and "
                            f"{result.optional_met} of {result.optional_total} optional ones."
                        ),
                        scoring_version=result.version,
                        started_at=submitted_at,
                        completed_at=submitted_at + timedelta(minutes=2),
                    )
                    screenings.append(screening)

                    for order, finding in enumerate(result.findings):
                        supplied = finding.verdict in {
                            DocumentScreeningVerdict.PRESENT,
                            DocumentScreeningVerdict.PRESENT_EXPIRED,
                        }
                        is_iso = (
                            finding.document_type is RequiredDocumentType.ISO_CERTIFICATION
                            and assessment is not None
                        )
                        findings.append(
                            ScreeningFinding(
                                screening_id=screening.id,
                                document_type=finding.document_type.value,
                                verdict=finding.verdict.value,
                                is_mandatory=finding.is_mandatory,
                                weight=finding.weight,
                                matched_document_id=bundle.id if supplied or is_iso else None,
                                source_page=(order % len(checklist)) + 1 if supplied else None,
                                note=(
                                    assessment.explanation
                                    if is_iso and assessment
                                    else finding.explanation
                                ),
                                display_order=order,
                            )
                        )

                    notifications.append(
                        Notification(
                            recipient_user_id=listing.owner_user_id,
                            type=NotificationType.SCREENING_COMPLETED.value,
                            title=f"{vendor_org.name} applied to {listing.title}",
                            body=(
                                f"Document screening scored {result.score}/100 with "
                                f"{result.mandatory_met} of {result.mandatory_total} mandatory "
                                "documents supplied."
                            ),
                            listing_id=listing.id,
                            application_id=application.id,
                            screening_score=result.score,
                        )
                    )
                    listing.application_count = (listing.application_count or 0) + 1
                    created += 1

            session.add_all(applications)
            await session.flush()
            session.add_all(documents)
            await session.flush()
            session.add_all(screenings)
            await session.flush()
            session.add_all(findings)
            session.add_all(notifications)
            await session.commit()

            unverified = sum(
                1
                for f in findings
                if f.verdict == DocumentScreeningVerdict.PRESENT_UNVERIFIED.value
            )

        print(
            f"\nSeeded {len(buyer_pairs)} buyers, {len(vendor_pairs)} vendors, "
            f"{len(listings)} published listings, {created} applications, "
            f"{len(fixtures)} certificates."
        )
        print(f"Findings needing verification (fake/unlisted certificate): {unverified}")
        print(f"Sign in with any @{DEMO_EMAIL_DOMAIN} address, password {DEMO_PASSWORD!r}.")
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
