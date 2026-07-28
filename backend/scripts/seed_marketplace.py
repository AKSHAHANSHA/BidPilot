"""Seed TenderSphere marketplace demo data.

Creates:
  - One company user (`gov-authority@tendersphere.ae`) posting the marketplace projects
  - One vendor user (`vendor@tendersphere.ae`) to demo the applicant flow
  - 8 marketplace projects across different categories
  - 2 applications from the demo vendor with pre-computed AI scores
  - A couple of notifications for the company account

Idempotent: re-running deletes and recreates the marketplace demo rows without touching the
original BidPilot demo (`seed_demo.py`).

    python scripts/seed_marketplace.py
    python scripts/seed_marketplace.py --reset

Runs against the same database as the API, using the same engine and session factory.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

from app.core.config import Settings, get_settings  # noqa: E402
from app.core.database import create_engine  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.domain.enums import (  # noqa: E402
    AccountType,
    ApplicationStatus,
    MarketProjectStatus,
    NotificationKind,
)
from app.models import (  # noqa: E402
    Application,
    MarketProject,
    Notification,
    User,
    VendorProfile,
)

COMPANY_EMAIL = "gov-authority@tendersphere.ae"
COMPANY_PASSWORD = "tendersphere-demo-passphrase-1"
COMPANY_DISPLAY_NAME = "Emirates Government Procurement Authority"

VENDOR_EMAIL = "vendor@tendersphere.ae"
VENDOR_PASSWORD = "tendersphere-vendor-passphrase-1"
VENDOR_DISPLAY_NAME = "Falcon Facilities LLC"


# Cover images: free Unsplash "source" URLs deterministically resolve to a themed photo. If
# they ever become unavailable the frontend falls back to a rendered placeholder.
def _cover(seed: str) -> str:
    return f"https://source.unsplash.com/1200x600/?{seed}"


PROJECT_SEEDS: tuple[dict[str, object], ...] = (
    {
        "title": "Metro Station Facilities Management (5-year contract)",
        "category": "facilities_management",
        "location": "Dubai",
        "budget_aed": Decimal("18500000.00"),
        "deadline_days": 21,
        "description": (
            "Comprehensive facilities management across 12 metro stations in Dubai. "
            "Scope covers HVAC maintenance, cleaning, security escort, minor civil works, "
            "and 24/7 helpdesk coverage. RTA compliance and ISO 41001 required."
        ),
        "requirements_summary": (
            "- ISO 41001 or equivalent FM certification\n"
            "- 5+ years of transit-authority experience in the GCC\n"
            "- Minimum AED 20M annual turnover\n"
            "- Local UAE presence with active trade licence\n"
            "- 24/7 operations capability"
        ),
        "cover": _cover("metro,station,transport"),
    },
    {
        "title": "National Hospital ICT Modernization",
        "category": "it_services",
        "location": "Abu Dhabi",
        "budget_aed": Decimal("32000000.00"),
        "deadline_days": 30,
        "description": (
            "Replace legacy HIS with a HL7 FHIR-compliant platform across 4 government "
            "hospitals. Includes network re-cabling, endpoint refresh, on-prem private "
            "cloud, and 3 years of managed operations."
        ),
        "requirements_summary": (
            "- MoH informatics vendor registration\n"
            "- HL7 FHIR + DICOM integration track record\n"
            "- ISO 27001 + HIPAA-equivalent controls\n"
            "- 24/7 SOC + Arabic-speaking L1 support"
        ),
        "cover": _cover("hospital,healthcare,it"),
    },
    {
        "title": "School Catering Framework Agreement",
        "category": "catering",
        "location": "Sharjah",
        "budget_aed": Decimal("4200000.00"),
        "deadline_days": 14,
        "description": (
            "Daily hot-meal catering across 22 public schools in Sharjah for the "
            "2026/2027 academic year. Halal, nutritionist-approved menus mandatory."
        ),
        "requirements_summary": (
            "- Dubai Municipality food safety grade A\n"
            "- HACCP + ISO 22000\n"
            "- Cold-chain logistics fleet"
        ),
        "cover": _cover("catering,school,food"),
    },
    {
        "title": "Solar Farm EPC — 120MW",
        "category": "energy_utilities",
        "location": "Al Ain",
        "budget_aed": Decimal("410000000.00"),
        "deadline_days": 45,
        "description": (
            "Design, procurement, and construction of a 120MW single-axis-tracking PV "
            "installation with 40MWh BESS. Full grid interconnection scope included."
        ),
        "requirements_summary": (
            "- 3+ EPC references of ≥100MW\n"
            "- ADWEA / EWEC prequalification\n"
            "- Local partner with civil-works trade licence"
        ),
        "cover": _cover("solar,farm,energy"),
    },
    {
        "title": "Government Building Cleaning (12 months)",
        "category": "cleaning",
        "location": "Dubai",
        "budget_aed": Decimal("2800000.00"),
        "deadline_days": 10,
        "description": (
            "Daily deep-clean of 8 ministry buildings, weekends included. Green cleaning "
            "chemicals and biodegradable consumables required."
        ),
        "requirements_summary": (
            "- Dubai Municipality cleaning contractor licence\n"
            "- ISO 14001\n"
            "- Trained staff ≥ 60 headcount"
        ),
        "cover": _cover("cleaning,office,building"),
    },
    {
        "title": "Airport Perimeter Security Uplift",
        "category": "security",
        "location": "Abu Dhabi",
        "budget_aed": Decimal("55000000.00"),
        "deadline_days": 28,
        "description": (
            "Perimeter fence hardening, CCTV mesh, AI-assisted intrusion detection, and "
            "armed response for a Category-A international airport."
        ),
        "requirements_summary": (
            "- SIRA Grade A licence\n"
            "- ICAO Annex 17 compliance experience\n"
            "- 24/7 armed-response capability"
        ),
        "cover": _cover("airport,security,perimeter"),
    },
    {
        "title": "Federal Uniform Supply — Traffic Police",
        "category": "uniforms_ppe",
        "location": "Dubai",
        "budget_aed": Decimal("6500000.00"),
        "deadline_days": 18,
        "description": (
            "Supply of 12,000 traffic police uniforms, boots, and reflective PPE with "
            "RFID-tagged inventory across a 3-year framework."
        ),
        "requirements_summary": (
            "- OEKO-TEX certified fabrics\n"
            "- ISO 9001\n"
            "- UAE local manufacturing preferred"
        ),
        "cover": _cover("uniform,police,fabric"),
    },
    {
        "title": "Municipal Waste-to-Energy Feasibility Study",
        "category": "environmental",
        "location": "Ras Al Khaimah",
        "budget_aed": Decimal("1400000.00"),
        "deadline_days": 12,
        "description": (
            "Full technical, environmental, and financial feasibility for a 400 t/day "
            "waste-to-energy plant. Deliverables include an EIA scoping document."
        ),
        "requirements_summary": (
            "- ISO 14001\n"
            "- 2+ WtE feasibility references in the MENA region"
        ),
        "cover": _cover("waste,recycling,plant"),
    },
)


async def _reset_marketplace(session, company_id, vendor_id) -> None:
    # Applications and notifications go first to satisfy FKs.
    await session.execute(delete(Application).where(Application.vendor_user_id == vendor_id))
    await session.execute(
        delete(MarketProject).where(MarketProject.posted_by_user_id == company_id)
    )
    await session.execute(
        delete(Notification).where(Notification.recipient_user_id.in_([company_id, vendor_id]))
    )


async def _get_or_create_user(session, *, email, password, display_name, account_type) -> User:
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is not None:
        # Update account_type in case it was pre-marketplace-backfilled to `vendor`.
        user.account_type = account_type
        return user
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name=display_name,
        is_active=True,
        account_type=account_type,
    )
    session.add(user)
    await session.flush()
    return user


async def seed(*, reset_only: bool = False) -> int:
    settings: Settings = get_settings()
    engine = create_engine(settings)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    now = datetime.now(tz=UTC)

    try:
        async with factory() as session:
            company = await _get_or_create_user(
                session,
                email=COMPANY_EMAIL,
                password=COMPANY_PASSWORD,
                display_name=COMPANY_DISPLAY_NAME,
                account_type=AccountType.COMPANY.value,
            )
            vendor = await _get_or_create_user(
                session,
                email=VENDOR_EMAIL,
                password=VENDOR_PASSWORD,
                display_name=VENDOR_DISPLAY_NAME,
                account_type=AccountType.VENDOR.value,
            )

            await _reset_marketplace(session, company.id, vendor.id)

            if reset_only:
                await session.commit()
                print("Marketplace demo reset complete.")
                return 0

            # Vendor profile
            vendor_profile_result = await session.execute(
                select(VendorProfile).where(VendorProfile.owner_user_id == vendor.id)
            )
            if vendor_profile_result.scalar_one_or_none() is None:
                session.add(
                    VendorProfile(
                        owner_user_id=vendor.id,
                        display_name=VENDOR_DISPLAY_NAME,
                        location="Dubai, UAE",
                        primary_category="facilities_management",
                        bio=(
                            "Falcon Facilities LLC delivers integrated FM services across "
                            "the UAE with 180 staff, ISO 41001 accreditation, and 12 years "
                            "of government-sector experience."
                        ),
                        contact_email=VENDOR_EMAIL,
                    )
                )

            # Projects
            projects: list[MarketProject] = []
            for seed_data in PROJECT_SEEDS:
                project = MarketProject(
                    posted_by_user_id=company.id,
                    title=str(seed_data["title"]),
                    company_display_name=COMPANY_DISPLAY_NAME,
                    description=str(seed_data["description"]),
                    category=str(seed_data["category"]),
                    location=str(seed_data["location"]),
                    budget_aed=seed_data["budget_aed"],  # type: ignore[arg-type]
                    submission_deadline=now + timedelta(days=int(seed_data["deadline_days"])),
                    cover_image_url=str(seed_data["cover"]),
                    requirements_summary=str(seed_data["requirements_summary"]),
                    is_public=True,
                    status=MarketProjectStatus.OPEN.value,
                )
                session.add(project)
                projects.append(project)
            await session.flush()

            # A couple of demo applications from the vendor so the dashboards are non-empty.
            demo_apps = (
                (
                    projects[0],
                    82,
                    ApplicationStatus.SCREENED.value,
                    "Strong FM background, ISO certifications match. Turnover slightly "
                    "below the AED 20M threshold — verify audited statements.",
                ),
                (
                    projects[4],
                    68,
                    ApplicationStatus.SCREENED.value,
                    "Cleaning capability confirmed. Missing ISO 14001 certificate in the "
                    "supplied portfolio — clarification required.",
                ),
            )
            for project, score, status, summary in demo_apps:
                app = Application(
                    project_id=project.id,
                    vendor_user_id=vendor.id,
                    ai_score=score,
                    ai_summary=summary,
                    ai_assessment={
                        "score": score,
                        "reasons": [summary],
                        "matched_categories": [project.category],
                    },
                    status=status,
                    submitted_at=now - timedelta(days=2),
                    reviewed_at=now - timedelta(days=1),
                )
                session.add(app)
                session.add(
                    Notification(
                        recipient_user_id=company.id,
                        kind=NotificationKind.APPLICATION_SCREENED.value,
                        title=f"New applicant for {project.title}",
                        body=(
                            f"{VENDOR_DISPLAY_NAME} applied with an AI screening score of "
                            f"{score}/100."
                        ),
                        payload={
                            "project_id": str(project.id),
                            "application_id": str(app.id),
                            "score": score,
                        },
                    )
                )

            await session.commit()

            print()
            print(f"  Company user:  {COMPANY_EMAIL} / {COMPANY_PASSWORD}")
            print(f"  Vendor user:   {VENDOR_EMAIL}  / {VENDOR_PASSWORD}")
            print(f"  Projects:      {len(PROJECT_SEEDS)}")
            print(f"  Applications:  {len(demo_apps)}")
            print()
            return 0
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the TenderSphere marketplace demo.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete marketplace demo data and exit.",
    )
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(level=settings.log_level_number, json_output=False)
    return asyncio.run(seed(reset_only=args.reset))


if __name__ == "__main__":
    raise SystemExit(main())
