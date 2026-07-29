"""Populate the marketplace with a browsable demo: buyers, vendors, listings and screenings.

Listings go through `ListingService`, so every seeded row obeys the same validators and publish
preconditions a real request would — a seed that bypassed the service could create a listing the
API itself can never produce.

Applications and screenings are built directly from the models, and deliberately so. A completed
screening is the *output* of the worker pipeline; reaching that state through the service layer
would mean running OCR and a language model over invented PDFs on every seed. Instead the
verdicts are stated as fixtures and the score is computed by the real
`app.domain.screening.calculate_screening_score` — the number in the demo is produced by
production code, not typed in.

Deadlines are offsets from today, so the demo always has tenders closing this week however long
after it was written the script is run.

    python scripts/seed_portal.py            # create or refresh
    python scripts/seed_portal.py --reset    # remove the demo accounts and everything they own
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import random
import sys
import textwrap
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app.core.config import Settings, get_settings  # noqa: E402
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
    NotificationType,
    RequiredDocumentType,
    ScreeningStatus,
    TenderCategory,
)
from app.domain.screening import (  # noqa: E402
    RequirementVerdict,
    ScreeningRequirement,
    ScreeningResult,
    calculate_screening_score,
)
from app.models.application import Application, ApplicationDocument  # noqa: E402
from app.models.certificate import CertificateRecord  # noqa: E402
from app.models.listing import ListingDocumentRequirement, TenderListing  # noqa: E402
from app.models.notification import Notification  # noqa: E402
from app.models.organisation import Organisation  # noqa: E402
from app.models.screening import ApplicationScreening, ScreeningFinding  # noqa: E402
from app.models.user import User  # noqa: E402
from app.repositories.application_repository import ApplicationRepository  # noqa: E402
from app.repositories.listing_repository import TenderListingRepository  # noqa: E402
from app.repositories.organisation_repository import OrganisationRepository  # noqa: E402
from app.schemas.listing import DocumentRequirementWrite, ListingCreate  # noqa: E402
from app.services.listing_service import ListingService  # noqa: E402
from app.storage.base import StorageBackend  # noqa: E402
from app.storage.local import LocalStorage  # noqa: E402
from scripts.certificate_fixtures import UNREGISTERED_NUMBERS, build_registry  # noqa: E402
from scripts.portal_fixtures import (  # noqa: E402
    BASE_MANDATORY,
    BASE_OPTIONAL,
    BUYERS,
    CATEGORY_REQUIREMENTS,
    TEMPLATES,
    VENDORS,
)

#: Every demo account shares this. Long enough for the password policy, and obviously a demo
#: credential rather than something that could be mistaken for a real one.
DEMO_PASSWORD = "bidpilot-demo-passphrase-2026"  # noqa: S105 - a published demo credential

#: Marks every account this script owns, so `--reset` can find them without touching a real
#: user who happens to be in the same database.
DEMO_EMAIL_DOMAIN = "portal-demo.bidpilot.local"

#: Fixed seed: re-running produces the same marketplace, so a screenshot taken today still
#: matches the demo tomorrow. `random` is used for spread, never for anything security-related.
RANDOM_SEED = 20260728


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")[:40]


def _email_for(name: str) -> str:
    return f"{_slug(name)}@{DEMO_EMAIL_DOMAIN}"


async def _reset(session: AsyncSession) -> int:
    """Delete every demo account. Cascades remove their organisations and listings."""
    rows = await session.execute(select(User).where(User.email.like(f"%@{DEMO_EMAIL_DOMAIN}")))
    users = list(rows.scalars())
    for user in users:
        await session.delete(user)
    await session.commit()
    return len(users)


async def _account(
    session: AsyncSession,
    *,
    name: str,
    description: str,
    account_type: AccountType,
    emirate: str,
    city: str,
    industry: str,
    employee_count: int | None = None,
    year_established: int | None = None,
) -> tuple[User, Organisation]:
    """Create a demo user and its organisation, or return the existing pair."""
    email = _email_for(name)
    existing = await session.execute(select(User).where(User.email == email))
    user = existing.scalar_one_or_none()
    if user is not None:
        organisation = await OrganisationRepository(session).get_for_owner(user.id)
        if organisation is not None:
            return user, organisation

    if user is None:
        user = User(
            email=email,
            password_hash=hash_password(DEMO_PASSWORD),
            display_name=f"{name} — demo account",
            account_type=account_type.value,
        )
        session.add(user)
        await session.flush()

    organisation = Organisation(
        owner_user_id=user.id,
        account_type=account_type.value,
        name=name,
        description=description,
        emirate=emirate,
        city=city,
        industry=industry,
        contact_email=f"contact@{_slug(name)}.example",
        employee_count=employee_count,
        year_established=year_established,
        # Buyers are shown with a verified badge so the demo can display both states.
        is_verified=account_type is AccountType.COMPANY,
    )
    session.add(organisation)
    await session.flush()
    return user, organisation


def _requirements_for(category: TenderCategory) -> list[DocumentRequirementWrite]:
    """Base checklist plus the category's own additions, deduplicated, buyer's order preserved."""
    seen: set[str] = set()
    items: list[DocumentRequirementWrite] = []

    def add(document_type: RequiredDocumentType, *, mandatory: bool, weight: int) -> None:
        if document_type.value in seen:
            return
        seen.add(document_type.value)
        items.append(
            DocumentRequirementWrite(
                document_type=document_type, is_mandatory=mandatory, weight=weight
            )
        )

    for document_type in BASE_MANDATORY:
        add(document_type, mandatory=True, weight=3)
    for document_type, mandatory in CATEGORY_REQUIREMENTS.get(category, ()):
        add(document_type, mandatory=mandatory, weight=5 if mandatory else 2)
    for document_type in BASE_OPTIONAL:
        add(document_type, mandatory=False, weight=1)
    return items


#: Suffixes that turn one template into several genuinely distinct procurements. Public
#: bodies really do split work this way — by geography, by phase, by lot — so this reads as a
#: programme rather than as padding. Every category is brought up to at least three listings so
#: neither the landing page nor a category filter can look empty.
LISTING_VARIANTS: tuple[tuple[str, float], ...] = (
    ("", 1.0),
    ("— northern package", 0.72),
    ("— phase 2", 1.24),
    ("— coastal zone lot", 0.61),
    ("— central district lot", 0.88),
)

MIN_LISTINGS_PER_CATEGORY = 3


def _category_plan(category: TenderCategory) -> list[tuple[object, str, float]]:
    """Template, title suffix and budget multiplier for each listing in a category."""
    templates = list(TEMPLATES.get(category, ()))
    if not templates:
        return []

    plan: list[tuple[object, str, float]] = [(t, "", 1.0) for t in templates]
    variant = 1
    # Cycle the variants over the templates until the category is populated. Distinct titles
    # matter more than the count, so the suffix always changes even when the template repeats.
    while len(plan) < MIN_LISTINGS_PER_CATEGORY and variant < len(LISTING_VARIANTS):
        suffix, multiplier = LISTING_VARIANTS[variant]
        plan.append((templates[(variant - 1) % len(templates)], suffix, multiplier))
        variant += 1
    return plan


async def _seed_listings(
    session: AsyncSession, settings: Settings, rng: random.Random
) -> list[TenderListing]:
    service = ListingService(
        listings=TenderListingRepository(session),
        organisations=OrganisationRepository(session),
        applications=ApplicationRepository(session),
        settings=settings,
    )

    now = datetime.now(tz=UTC)
    published: list[TenderListing] = []
    sequence = 0

    for buyer in BUYERS:
        user, organisation = await _account(
            session,
            name=str(buyer["name"]),
            description=str(buyer["description"]),
            account_type=AccountType.COMPANY,
            emirate=str(buyer["emirate"]),
            city=str(buyer["city"]),
            industry=str(buyer["industry"]),
        )

        for category in buyer["categories"]:  # type: ignore[union-attr]
            for template, suffix, budget_scale in _category_plan(category):
                sequence += 1
                # Deadlines fan out from next week to three months, so the "closing soon" badge,
                # the deadline sort and the closing-window filter all have something to show.
                days_ahead = 5 + (sequence * 7) % 88
                deadline = (now + timedelta(days=days_ahead)).replace(
                    hour=13, minute=0, second=0, microsecond=0
                )
                low, high = template.budget
                budget_min = Decimal(int(low * budget_scale))
                budget_max = Decimal(int(high * budget_scale))

                payload = ListingCreate(
                    title=f"{template.title} {suffix}".strip(),
                    summary=template.summary,
                    description=template.description,
                    category=category,
                    industry=str(buyer["industry"]),
                    reference=f"{_slug(str(buyer['name']))[:6].upper()}-2026-{sequence:03d}",
                    tags=list(template.tags),
                    emirate=organisation.emirate,  # type: ignore[arg-type]
                    city=organisation.city,
                    budget_min=budget_min,
                    budget_max=budget_max,
                    submission_deadline=deadline,
                    questions_deadline=deadline - timedelta(days=10),
                    contract_duration_months=template.duration_months,
                    min_years_experience=template.min_years_experience,
                    requires_bid_bond=template.requires_bid_bond,
                    bid_bond_percentage=Decimal("2.00") if template.requires_bid_bond else None,
                )

                listing = await service.create_listing(user_id=user.id, payload=payload)
                await service.replace_requirements(
                    user_id=user.id,
                    listing_id=listing.id,
                    items=_requirements_for(category),
                )
                # Publishing is the same guarded transition the API exposes: a listing that
                # cannot legitimately be published will raise here rather than be forced.
                listing = await service.publish(user_id=user.id, listing_id=listing.id)
                published.append(listing)

        await session.commit()

    rng.shuffle(published)
    return published


#: Realistic screening outcomes. Most vendors supply most things; the interesting demo states
#: are the near-miss and the one with an expired certificate.
VERDICT_PROFILES: tuple[tuple[str, tuple[DocumentScreeningVerdict, ...]], ...] = (
    ("complete", (DocumentScreeningVerdict.PRESENT,)),
    (
        "one_expired",
        (DocumentScreeningVerdict.PRESENT, DocumentScreeningVerdict.PRESENT_EXPIRED),
    ),
    (
        "missing_optional",
        (DocumentScreeningVerdict.PRESENT, DocumentScreeningVerdict.MISSING),
    ),
    (
        "blocking_gap",
        (
            DocumentScreeningVerdict.PRESENT,
            DocumentScreeningVerdict.MISSING,
            DocumentScreeningVerdict.PRESENT_UNREADABLE,
        ),
    ),
)


def _verdict_for(
    profile: tuple[DocumentScreeningVerdict, ...],
    *,
    index: int,
    is_mandatory: bool,
    rng: random.Random,
) -> DocumentScreeningVerdict:
    """Pick a verdict, keeping mandatory items mostly satisfied so scores stay plausible."""
    if index < 3:
        # The base identity documents are almost always supplied.
        return DocumentScreeningVerdict.PRESENT
    choice = profile[rng.randrange(len(profile))]
    if is_mandatory and choice is DocumentScreeningVerdict.MISSING and rng.random() < 0.55:
        return DocumentScreeningVerdict.PRESENT
    return choice


#: Verdicts that assert a document was found. The database requires each of these to name the
#: upload it was matched in — see `ck_screening_findings_present_needs_document`.
_EVIDENCED_VERDICTS = frozenset(
    {DocumentScreeningVerdict.PRESENT, DocumentScreeningVerdict.PRESENT_EXPIRED}
)


def _evidence_line(vendor_name: str, document_type: RequiredDocumentType, *, expired: bool) -> str:
    """The sentence a screening finding will quote. Written onto the page it cites."""
    label = document_type.value.replace("_", " ")
    state = "expired on 31 December 2025" if expired else "is valid to 31 December 2027"
    return f"This document certifies that {vendor_name} holds a current {label}, which {state}."


def _build_submission_bundle(
    vendor_name: str,
    entries: Sequence[tuple[RequiredDocumentType, bool]],
    *,
    certificate_number: str | None = None,
) -> tuple[bytes, dict[str, int], dict[str, str]]:
    """Render one multi-page PDF standing in for the vendor's uploaded document pack.

    A real bundle rather than a metadata-only row: findings cite a page and quote its text, and
    a demo whose citations point at a file that does not exist would be demonstrating exactly
    the thing this product refuses to do. One file per application, one page per supplied
    document, so the page a finding cites genuinely contains the sentence it quotes.

    Returns the PDF bytes, the page number per document type, and the quoted line per type.
    """
    import fitz  # imported here so the seeder's import cost is paid only when it runs

    document = fitz.open()
    pages: dict[str, int] = {}
    quotes: dict[str, str] = {}

    for index, (document_type, expired) in enumerate(entries, start=1):
        page = document.new_page()
        line = _evidence_line(vendor_name, document_type, expired=expired)
        heading = document_type.value.replace("_", " ").upper()
        page.insert_text((60, 90), heading, fontsize=15)
        page.insert_text((60, 130), vendor_name, fontsize=11)
        # Wrapped by hand: insert_text draws one line and would otherwise run off the page,
        # which would put half the quoted sentence outside the extractable text.
        wrapped = textwrap.wrap(line, width=78)
        for offset, chunk in enumerate(wrapped):
            page.insert_text((60, 165 + offset * 18), chunk, fontsize=10)
        if document_type is RequiredDocumentType.ISO_CERTIFICATION and certificate_number:
            # Printed on the page so the pipeline's extractor finds it exactly as it would in a
            # real upload — the seeded bundle is not a special case.
            page.insert_text((60, 215), f"Certificate number: {certificate_number}", fontsize=10)
        page.insert_text((60, 260), "Issued for tender submission purposes.", fontsize=9)
        pages[document_type.value] = index
        # Quote a single rendered line, not the unwrapped sentence: extraction returns the text
        # as it was drawn, so a quote spanning the wrap would not match the page verbatim.
        quotes[document_type.value] = wrapped[0]

    payload: bytes = document.tobytes()
    document.close()
    return payload, pages, quotes


async def _seed_certificates(
    session: AsyncSession, vendor_names: tuple[str, ...], *, rng: random.Random
) -> int:
    """Load the accreditation register.

    Reference data, so it is replaced wholesale rather than merged: the generator is
    deterministic, and a partial refresh would leave numbers from an older seed that nothing
    points at any more.
    """
    await session.execute(delete(CertificateRecord))
    today = datetime.now(tz=UTC).date()
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
    return len(fixtures)


async def _pick_certificate(
    session: AsyncSession, vendor_name: str, *, rng: random.Random
) -> tuple[str, RegisteredCertificate | None]:
    """Choose the certificate number this submission will print, and the register's answer.

    Roughly a fifth of submissions carry a number that is not in the register. That is the case
    the whole feature exists to catch, and a demo where every certificate verifies would never
    show it.
    """
    roll = rng.random()
    if roll < 0.20:
        return UNREGISTERED_NUMBERS[rng.randrange(len(UNREGISTERED_NUMBERS))], None

    # Prefer one of this vendor's own certificates; fall back to any active row.
    rows = await session.execute(
        select(CertificateRecord)
        .where(CertificateRecord.issued_to == vendor_name)
        .order_by(CertificateRecord.display_number)
    )
    owned = list(rows.scalars())
    if not owned:
        any_rows = await session.execute(select(CertificateRecord).limit(20))
        owned = list(any_rows.scalars())
    if not owned:
        return UNREGISTERED_NUMBERS[0], None

    record = owned[rng.randrange(len(owned))]
    return record.display_number, RegisteredCertificate(
        number=record.certificate_number,
        display_number=record.display_number,
        standard=record.standard,
        issued_to=record.issued_to,
        issuing_body=record.issuing_body,
        status=record.status,
        expires_on=record.expires_on,
    )


async def _seed_applications(
    session: AsyncSession,
    listings: list[TenderListing],
    rng: random.Random,
    storage: StorageBackend,
) -> int:
    now = datetime.now(tz=UTC)
    created = 0

    for vendor in VENDORS:
        user, organisation = await _account(
            session,
            name=str(vendor["name"]),
            description=str(vendor["description"]),
            account_type=AccountType.VENDOR,
            emirate=str(vendor["emirate"]),
            city=str(vendor["city"]),
            industry=str(vendor["industry"]),
            employee_count=int(vendor["employee_count"]),  # type: ignore[arg-type]
            year_established=int(vendor["year_established"]),  # type: ignore[arg-type]
        )

        # Enough applications to make the dashboard's charts and win rate meaningful.
        for listing in listings[:14]:
            # Eager-load the checklist: a lazy load here would be a synchronous IO call inside
            # an async stack, which raises MissingGreenlet rather than fetching anything.
            loaded = await session.execute(
                select(TenderListing)
                .where(TenderListing.id == listing.id)
                .options(selectinload(TenderListing.document_requirements))
            )
            listing_full = loaded.scalar_one_or_none()
            if listing_full is None:
                continue
            requirements = listing_full.document_requirements
            if not requirements:
                continue

            profile_name, profile = VERDICT_PROFILES[rng.randrange(len(VERDICT_PROFILES))]

            # If the buyer asked for an ISO certificate, the verdict is not a fixture: the
            # submission prints a real number and `assess_certificate` — the same function the
            # live pipeline calls — decides what it is worth. That is what makes the seeded
            # demo and the running product incapable of disagreeing.
            wants_iso = any(
                _as_doc_type(item) is RequiredDocumentType.ISO_CERTIFICATION
                for item in requirements
            )
            certificate_number: str | None = None
            assessment = None
            if wants_iso:
                certificate_number, record = await _pick_certificate(
                    session, organisation.name, rng=rng
                )
                assessment = assess_certificate(
                    CertificateCandidate(
                        number=normalize_certificate_number(certificate_number),
                        raw=certificate_number,
                        standard="ISO 9001",
                        page=1,
                    ),
                    record,
                )

            verdicts = []
            for index, item in enumerate(requirements):
                document_type = _as_doc_type(item)
                if document_type is RequiredDocumentType.ISO_CERTIFICATION and assessment:
                    verdict = assessment.verdict
                else:
                    verdict = _verdict_for(
                        profile, index=index, is_mandatory=item.is_mandatory, rng=rng
                    )
                verdicts.append(
                    RequirementVerdict(
                        requirement=ScreeningRequirement(
                            document_type=document_type,
                            is_mandatory=item.is_mandatory,
                            weight=item.weight,
                        ),
                        verdict=verdict,
                    )
                )
            result = calculate_screening_score(verdicts)

            budget_high = listing_full.budget_max or listing_full.budget_min or Decimal(1_000_000)
            bid = (budget_high * Decimal(rng.randrange(82, 99))) / Decimal(100)
            cost = (bid * Decimal(rng.randrange(72, 93))) / Decimal(100)

            status, decided_at = _outcome(result.has_blocking_gap, rng=rng, now=now)
            submitted_at = now - timedelta(days=rng.randrange(3, 60))

            application = Application(
                listing_id=listing_full.id,
                vendor_user_id=user.id,
                vendor_organisation_id=organisation.id,
                status=status.value,
                cover_letter=(
                    f"{organisation.name} is pleased to submit a proposal for "
                    f"{listing_full.title}. Our team has delivered comparable work across the "
                    "UAE and can mobilise within four weeks of award."
                ),
                bid_amount=bid.quantize(Decimal("0.01")),
                estimated_cost=cost.quantize(Decimal("0.01")),
                proposed_duration_months=listing_full.contract_duration_months,
                submitted_at=submitted_at,
                decided_at=decided_at,
                first_viewed_at=submitted_at + timedelta(days=1),
                decision_note=(
                    "Strongest technical response with a credible programme."
                    if status is ApplicationStatus.APPROVED
                    else "Another bidder scored higher on technical capability."
                    if status is ApplicationStatus.REJECTED
                    else None
                ),
            )
            session.add(application)
            await session.flush()

            # One uploaded bundle per application, containing a page for each supplied
            # document. Written to storage so the findings below cite a file that exists.
            evidenced = [
                (finding.document_type, finding.verdict is DocumentScreeningVerdict.PRESENT_EXPIRED)
                for finding in result.findings
                if finding.verdict in _EVIDENCED_VERDICTS
            ]
            # An unverified certificate was still uploaded. Its page belongs in the bundle so
            # the vendor can see the number that was checked and disagree with it if we are
            # wrong — the opposite of hiding the evidence behind a rejection.
            if assessment and not assessment.is_credited:
                evidenced.append((RequiredDocumentType.ISO_CERTIFICATION, False))
            document_id: uuid.UUID | None = None
            pages: dict[str, int] = {}
            quotes: dict[str, str] = {}
            if evidenced:
                payload, pages, quotes = _build_submission_bundle(
                    organisation.name, evidenced, certificate_number=certificate_number
                )
                stored_filename = f"{uuid.uuid4().hex}.pdf"
                storage_key = f"{user.id}/applications/{application.id}/{stored_filename}"
                await storage.save(storage_key, payload)
                bundle = ApplicationDocument(
                    application_id=application.id,
                    vendor_user_id=user.id,
                    original_filename="submission-bundle.pdf",
                    stored_filename=stored_filename,
                    storage_key=storage_key,
                    mime_type="application/pdf",
                    size_bytes=len(payload),
                    sha256=hashlib.sha256(payload).hexdigest(),
                    page_count=len(evidenced),
                    extraction_status=DocumentExtractionStatus.EXTRACTED.value,
                )
                session.add(bundle)
                await session.flush()
                document_id = bundle.id

            screening = ApplicationScreening(
                application_id=application.id,
                status=ScreeningStatus.COMPLETED.value,
                overall_score=result.score,
                mandatory_met=result.mandatory_met,
                mandatory_total=result.mandatory_total,
                optional_met=result.optional_met,
                optional_total=result.optional_total,
                documents_processed=len(requirements),
                pages_extracted=len(requirements) * 3,
                pages_needing_ocr=1 if profile_name == "blocking_gap" else 0,
                summary=_summary(organisation.name, result),
                scoring_version=result.version,
                started_at=submitted_at,
                completed_at=submitted_at + timedelta(minutes=2),
            )
            session.add(screening)
            await session.flush()

            for order, finding in enumerate(result.findings):
                supplied = finding.verdict in _EVIDENCED_VERDICTS
                session.add(
                    ScreeningFinding(
                        screening_id=screening.id,
                        document_type=finding.document_type.value,
                        verdict=finding.verdict.value,
                        is_mandatory=finding.is_mandatory,
                        weight=finding.weight,
                        # A supplied verdict names the upload, the page and the sentence it was
                        # matched on — the same evidence the pipeline is required to produce.
                        matched_document_id=document_id if supplied else None,
                        source_page=pages.get(finding.document_type.value) if supplied else None,
                        evidence_quote=(
                            quotes.get(finding.document_type.value) if supplied else None
                        ),
                        note=(
                            assessment.explanation
                            if assessment
                            and finding.document_type is RequiredDocumentType.ISO_CERTIFICATION
                            else finding.explanation
                        ),
                        display_order=order,
                    )
                )

            session.add(
                Notification(
                    recipient_user_id=listing_full.owner_user_id,
                    type=NotificationType.SCREENING_COMPLETED.value,
                    title=f"{organisation.name} applied to {listing_full.title}",
                    body=(
                        f"Document screening scored {result.score}/100 with "
                        f"{result.mandatory_met} of {result.mandatory_total} mandatory documents "
                        "supplied."
                    ),
                    listing_id=listing_full.id,
                    application_id=application.id,
                    screening_score=result.score,
                )
            )
            created += 1

        await session.commit()
        rng.shuffle(listings)

    return created


def _as_doc_type(item: ListingDocumentRequirement) -> RequiredDocumentType:
    """The ORM stores the vocabulary as a plain string; the scorer wants the enum member."""
    return RequiredDocumentType(item.document_type)


def _outcome(
    blocking: bool, *, rng: random.Random, now: datetime
) -> tuple[ApplicationStatus, datetime | None]:
    """Spread outcomes across the dashboard's buckets, weighted by whether a gap was found."""
    roll = rng.random()
    if blocking:
        if roll < 0.55:
            return ApplicationStatus.REJECTED, now - timedelta(days=rng.randrange(1, 20))
        return ApplicationStatus.UNDER_REVIEW, None
    if roll < 0.28:
        return ApplicationStatus.APPROVED, now - timedelta(days=rng.randrange(1, 25))
    if roll < 0.45:
        return ApplicationStatus.REJECTED, now - timedelta(days=rng.randrange(1, 25))
    if roll < 0.68:
        return ApplicationStatus.SHORTLISTED, None
    if roll < 0.86:
        return ApplicationStatus.UNDER_REVIEW, None
    return ApplicationStatus.SUBMITTED, None


def _summary(vendor_name: str, result: ScreeningResult) -> str:
    """Advisory narrative, built only from the validated findings."""
    if result.score is None:
        return "This tender listed no documents to assess."
    parts = [
        f"{vendor_name} supplied {result.mandatory_met} of {result.mandatory_total} mandatory "
        f"documents and {result.optional_met} of {result.optional_total} optional ones."
    ]
    if result.missing:
        names = ", ".join(finding.label for finding in result.missing[:3])
        parts.append(
            f"Not found in the submitted documents: {names}. This reflects what was uploaded, "
            "not a conclusion that the bidder lacks them."
        )
    if result.unreadable:
        parts.append(
            f"{len(result.unreadable)} document(s) could not be read and were not assessed."
        )
    return " ".join(parts)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="delete the demo accounts and exit")
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(level=settings.log_level_number, json_output=False)
    settings.ensure_directories()
    engine = create_engine(settings)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    # Local filesystem regardless of STORAGE_BACKEND: the seeder writes demo bundles and must
    # not push them into a configured production bucket.
    storage: StorageBackend = LocalStorage(settings.upload_dir)
    rng = random.Random(RANDOM_SEED)  # noqa: S311 - demo spread, not security

    try:
        async with factory() as session:
            removed = await _reset(session)
            if args.reset:
                print(f"Removed {removed} demo account(s).")
                return 0
            if removed:
                print(f"Cleared {removed} existing demo account(s) before reseeding.")

            vendor_names = tuple(str(v["name"]) for v in VENDORS)
            certificates = await _seed_certificates(session, vendor_names, rng=rng)
            listings = await _seed_listings(session, settings, rng)
            applications = await _seed_applications(session, listings, rng, storage)

        print(
            f"\nSeeded {len(BUYERS)} buyers, {len(VENDORS)} vendors, {len(listings)} published "
            f"listings, {applications} applications and {certificates} register certificates."
        )
        print(f"Sign in with any demo address @{DEMO_EMAIL_DOMAIN} and password {DEMO_PASSWORD!r}.")
        print(f"  buyer:  {_email_for(str(BUYERS[0]['name']))}")
        print(f"  vendor: {_email_for(str(VENDORS[0]['name']))}")
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
