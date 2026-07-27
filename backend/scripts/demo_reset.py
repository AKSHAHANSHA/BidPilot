"""Reset the demo to a known, clean state in one command.

    python scripts/demo_reset.py

Deletes every tender owned by the demo user (cascading to its documents, pages, analyses, and
findings) and then re-seeds the fictional company, evidence, and projects via `seed_demo.seed`.
The result is the exact state a reviewer should see on first sign-in: a fully populated company
and no prior analyses. Idempotent and safe to run repeatedly.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import create_engine  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.models.tender import Tender  # noqa: E402
from app.models.user import User  # noqa: E402
from scripts.seed_demo import FIXTURE_PATH, seed  # noqa: E402


async def _clear_demo_tenders() -> int:
    settings = get_settings()
    demo_email = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["user"]["email"]
    engine = create_engine(settings)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    try:
        async with factory() as session:
            user = (
                await session.execute(select(User).where(User.email == demo_email))
            ).scalar_one_or_none()
            if user is None:
                return 0
            # ORM-level delete so the tender -> documents/analyses cascades fire.
            tenders = (
                (await session.execute(select(Tender).where(Tender.owner_user_id == user.id)))
                .scalars()
                .all()
            )
            for tender in tenders:
                await session.delete(tender)
            await session.commit()
            return len(tenders)
    finally:
        await engine.dispose()


async def _reset() -> int:
    removed = await _clear_demo_tenders()
    print(f"Removed {removed} demo tender(s) and their analyses.")
    return await seed()


def main() -> int:
    settings = get_settings()
    configure_logging(level=settings.log_level_number, json_output=False)
    return asyncio.run(_reset())


if __name__ == "__main__":
    raise SystemExit(main())
