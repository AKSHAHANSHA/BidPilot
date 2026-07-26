"""Row factories for integration tests.

Repository-level helpers only. Tests that exercise the API build state through HTTP instead, so
they cannot accidentally create rows the API itself could never produce.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.company_profile import CompanyProfile
from app.models.user import User
from app.repositories.user_repository import UserRepository

DEMO_PASSWORD = "a-long-demo-passphrase-1"


async def make_user(session: AsyncSession, label: str = "owner") -> User:
    users = UserRepository(session)
    user = users.create(
        email=f"{label}-{uuid.uuid4().hex[:10]}@fm-demo.ae",
        password_hash=hash_password(DEMO_PASSWORD),
        display_name=label.title(),
    )
    await users.flush()
    return user


async def make_profile(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    **overrides: object,
) -> CompanyProfile:
    today = datetime.now(tz=UTC).date()
    values: dict[str, object] = {
        "legal_name": "Al Mirqab Integrated Facilities Management LLC",
        "description": "A Dubai-based integrated facilities management provider for towers.",
        "industry": "Facilities Management",
        "emirate": "dubai",
        "country": "United Arab Emirates",
        "year_established": 2011,
        "employee_count": 84,
        "years_of_experience": 14,
        "trade_licence_number": "DED-000-DEMO-4471",
        "trade_licence_expiry": today + timedelta(days=210),
        "licence_activities": ["Building cleaning services"],
        "contact_email": "tenders@fm-demo.ae",
        "service_categories": ["Hard FM"],
        "geographic_coverage": ["Dubai"],
        "preferred_contract_value_min": Decimal("500000.00"),
        "preferred_contract_value_max": Decimal("12000000.00"),
    }
    values.update(overrides)
    profile = CompanyProfile(owner_user_id=owner_user_id, **values)
    session.add(profile)
    await session.flush()
    return profile


def valid_profile_payload(**overrides: object) -> dict[str, object]:
    """A request body that passes every validator, for API-level tests."""
    today = datetime.now(tz=UTC).date()
    payload: dict[str, object] = {
        "legal_name": "Al Mirqab Integrated Facilities Management LLC",
        "trading_name": "Al Mirqab FM",
        "description": (
            "A Dubai-based integrated facilities management provider delivering hard and soft "
            "FM services across the northern emirates."
        ),
        "industry": "Facilities Management",
        "emirate": "dubai",
        "country": "United Arab Emirates",
        "year_established": 2011,
        "employee_count": 84,
        "years_of_experience": 14,
        "trade_licence_number": "DED-000-DEMO-4471",
        "trade_licence_expiry": (today + timedelta(days=210)).isoformat(),
        # Three of each list field, so the default payload scores a full 100 and any shortfall in
        # a test is caused by that test's own override rather than by thin fixture data.
        "licence_activities": ["Building cleaning services", "HVAC maintenance", "Pest control"],
        "website": "https://almirqab-fm.example.ae",
        "contact_email": "tenders@fm-demo.ae",
        "contact_phone": "+971 4 000 0000",
        "annual_revenue_range": "5m_to_20m_aed",
        "preferred_contract_value_min": "500000.00",
        "preferred_contract_value_max": "12000000.00",
        "service_categories": ["Hard FM", "Soft FM", "HVAC maintenance"],
        "geographic_coverage": ["Dubai", "Sharjah"],
    }
    payload.update(overrides)
    return payload


def valid_evidence_payload(**overrides: object) -> dict[str, object]:
    today = datetime.now(tz=UTC).date()
    payload: dict[str, object] = {
        "title": "ISO 9001:2015 Quality Management Certification",
        "category": "certification",
        "issuing_organisation": "Fictional Certification Bureau (demo)",
        "reference_number": "FCB-QMS-DEMO-2024-118",
        "description": "Quality management system certification covering FM service delivery.",
        "issue_date": (today - timedelta(days=480)).isoformat(),
        "expiry_date": (today + timedelta(days=615)).isoformat(),
        "verification_status": "verified",
        "tags": ["iso", "quality"],
    }
    payload.update(overrides)
    return payload


def valid_project_payload(**overrides: object) -> dict[str, object]:
    today = datetime.now(tz=UTC).date()
    payload: dict[str, object] = {
        "client_name": "Fictional Retail Holdings (demo)",
        "project_title": "Integrated FM - Riverside Retail Centre",
        "industry": "Retail",
        "description": "Full soft and hard FM delivery across a 42,000 sqm retail centre.",
        "contract_value": "8400000.00",
        "currency": "AED",
        "start_date": (today - timedelta(days=1460)).isoformat(),
        "end_date": (today - timedelta(days=365)).isoformat(),
        "status": "completed",
        "location": "Dubai",
        "services_delivered": ["Soft FM", "Hard FM"],
        "outcome": "Delivered to SLA for three consecutive years.",
        "client_reference_available": True,
        "is_confidential": False,
    }
    payload.update(overrides)
    return payload


def iso(offset_days: int) -> str:
    return (datetime.now(tz=UTC).date() + timedelta(days=offset_days)).isoformat()


def today_date() -> date:
    return datetime.now(tz=UTC).date()
