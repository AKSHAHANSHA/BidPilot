"""Load the fictional demo company from `sample_data/demo_company.json`.

Deliberately not a general seeding framework. It loads one fixture through the same services the
API uses, so the seeded rows obey every validator and constraint a real request would — a seed
that bypassed the service layer could create state the API can never produce.

Dates in the fixture are stored as offsets from today rather than absolute values, so the demo
always shows a licence in date, an insurance policy genuinely expiring soon, and projects with
plausible recency, however long after Phase 2 the demo is run.

Idempotent: re-running replaces the demo user's profile, evidence, and projects.

    python scripts/seed_demo.py            # create or refresh
    python scripts/seed_demo.py --reset    # delete the demo profile and exit
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

from app.core.config import Settings, get_settings  # noqa: E402
from app.core.database import create_engine  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.domain.completion import calculate_completion  # noqa: E402
from app.domain.enums import ExpiryState  # noqa: E402
from app.repositories.company_repository import (  # noqa: E402
    CompanyEvidenceRepository,
    CompanyProfileRepository,
    CompanyProjectRepository,
    EvidenceFilters,
)
from app.repositories.user_repository import UserRepository  # noqa: E402
from app.schemas.company import CompanyProfileCreate  # noqa: E402
from app.schemas.evidence import EvidenceCreate  # noqa: E402
from app.schemas.project import ProjectCreate  # noqa: E402
from app.services.company_service import CompanyService  # noqa: E402

FIXTURE_PATH = BACKEND_ROOT / "sample_data" / "demo_company.json"


def _shift(offset_days: int | None, *, today: date) -> date | None:
    return None if offset_days is None else today + timedelta(days=offset_days)


def _build_profile_payload(raw: dict[str, Any], *, today: date) -> CompanyProfileCreate:
    values = {key: value for key, value in raw.items() if not key.endswith("_offset_days")}
    expiry = _shift(raw["trade_licence_expiry_offset_days"], today=today)
    return CompanyProfileCreate.model_validate({**values, "trade_licence_expiry": expiry})


def _build_evidence_payload(raw: dict[str, Any], *, today: date) -> EvidenceCreate:
    values = {key: value for key, value in raw.items() if not key.endswith("_offset_days")}
    return EvidenceCreate.model_validate(
        {
            **values,
            "issue_date": _shift(raw.get("issue_date_offset_days"), today=today),
            "expiry_date": _shift(raw.get("expiry_date_offset_days"), today=today),
        }
    )


def _build_project_payload(raw: dict[str, Any], *, today: date) -> ProjectCreate:
    values = {key: value for key, value in raw.items() if not key.endswith("_offset_days")}
    return ProjectCreate.model_validate(
        {
            **values,
            "start_date": _shift(raw["start_date_offset_days"], today=today),
            "end_date": _shift(raw.get("end_date_offset_days"), today=today),
            "contract_value": (
                Decimal(values["contract_value"]) if values.get("contract_value") else None
            ),
        }
    )


async def seed(*, reset_only: bool = False) -> int:
    settings: Settings = get_settings()
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    today = datetime.now(tz=UTC).date()

    engine = create_engine(settings)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    try:
        async with factory() as session:
            users = UserRepository(session)
            service = CompanyService(
                profiles=CompanyProfileRepository(session),
                evidence=CompanyEvidenceRepository(session),
                projects=CompanyProjectRepository(session),
                settings=settings,
            )

            demo = fixture["user"]
            user = await users.get_by_email(demo["email"])
            if user is None:
                if reset_only:
                    print("No demo user exists; nothing to reset.")
                    return 0
                user = users.create(
                    email=demo["email"],
                    password_hash=hash_password(demo["password"]),
                    display_name=demo["display_name"],
                )
                await users.flush()
                print(f"Created demo user {demo['email']}")
            else:
                print(f"Reusing demo user {demo['email']}")

            # Cascades to the user's evidence and projects, which is what makes this idempotent.
            existing = await service.profiles.get_for_owner(user.id)
            if existing is not None:
                await service.profiles.delete(existing)
                await service.profiles.flush()
                print("Removed the previous demo company profile (cascaded to its children)")

            if reset_only:
                await session.commit()
                print("Reset complete.")
                return 0

            profile = await service.create_profile(
                user_id=user.id,
                payload=_build_profile_payload(fixture["profile"], today=today),
            )

            for raw in fixture["evidence"]:
                await service.create_evidence(
                    user_id=user.id, payload=_build_evidence_payload(raw, today=today)
                )

            for raw in fixture["projects"]:
                await service.create_project(
                    user_id=user.id, payload=_build_project_payload(raw, today=today)
                )

            await session.commit()

            completion = calculate_completion(profile)
            evidence_counts = await service.evidence.count_by_category(user.id)

            # Report the derived expiry spread, which is the point of the fixture's offsets:
            # the insurance policy should land in `expiring_soon` on any day the demo is run.
            expiry_spread: dict[str, int] = {}
            for state in ExpiryState:
                _, count = await service.list_evidence(
                    user_id=user.id,
                    filters=EvidenceFilters(expiry_state=state),
                    limit=1,
                    offset=0,
                )
                if count:
                    expiry_spread[state.value] = count

            print()
            print(f"  Company:            {profile.legal_name}")
            print(f"  Profile completion: {completion.score}% (v{completion.version})")
            print(f"  Evidence items:     {sum(evidence_counts.values())}")
            for category, count in sorted(evidence_counts.items()):
                print(f"    - {category}: {count}")
            print(f"  Expiry states:      {expiry_spread}")
            print(f"  Projects:           {len(fixture['projects'])}")
            print()
            print(f"  Sign in with: {demo['email']} / {demo['password']}")
            return 0
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the fictional demo company.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the demo company profile and its children, then exit.",
    )
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(level=settings.log_level_number, json_output=False)
    return asyncio.run(seed(reset_only=args.reset))


if __name__ == "__main__":
    raise SystemExit(main())
