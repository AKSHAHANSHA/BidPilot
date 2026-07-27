"""Migrations must run forward and backward against real PostgreSQL.

Alembic is driven through `asyncio.to_thread` because `migrations/env.py` calls
`asyncio.run(...)`, which cannot be nested inside the test's running event loop. Running it in
a worker thread gives it a clean thread with no loop, exactly as the CLI has.
"""

from __future__ import annotations

import asyncio

import pytest
from alembic import command
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import create_engine
from tests.integration.conftest import alembic_config

pytestmark = pytest.mark.integration

EXPECTED_HEAD = "0009"
EXPECTED_TABLES = (
    "users",
    "refresh_sessions",
    "company_profiles",
    "company_evidence",
    "company_projects",
    "tenders",
    "documents",
    "document_pages",
    "analyses",
    "requirements",
    "requirement_citations",
    "tender_metadata",
    "requirement_evidence_matches",
    "risk_findings",
    "risk_citations",
    "readiness_assessments",
)


async def upgrade(target: str = "head") -> None:
    await asyncio.to_thread(command.upgrade, alembic_config(), target)


async def downgrade(target: str) -> None:
    await asyncio.to_thread(command.downgrade, alembic_config(), target)


async def read_revision() -> str | None:
    """Revision recorded in the database.

    None means the bookkeeping table is absent or empty — Alembic keeps the table after
    `downgrade base` and only deletes the row.
    """
    engine = create_engine(get_settings())
    try:
        async with engine.connect() as connection:
            exists = await connection.execute(
                text("SELECT to_regclass('alembic_version') IS NOT NULL")
            )
            if not exists.scalar_one():
                return None
            result = await connection.execute(text("SELECT version_num FROM alembic_version"))
            return result.scalar_one_or_none()
    finally:
        await engine.dispose()


async def table_exists(name: str) -> bool:
    engine = create_engine(get_settings())
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text("SELECT to_regclass(:name) IS NOT NULL"), {"name": name}
            )
            return bool(result.scalar_one())
    finally:
        await engine.dispose()


@pytest.fixture(autouse=True)
async def restore_head() -> None:
    """Leave the database at head however the test ends.

    These tests deliberately move the schema around; every other integration test assumes a
    migrated database, and test execution order must not decide whether they pass.
    """
    await downgrade("base")
    yield
    await upgrade("head")


async def test_upgrade_head_records_the_latest_revision() -> None:
    await upgrade()
    assert await read_revision() == EXPECTED_HEAD


@pytest.mark.parametrize("table", EXPECTED_TABLES)
async def test_upgrade_creates_expected_tables(table: str) -> None:
    await upgrade()
    assert await table_exists(table) is True


async def test_downgrade_to_base_removes_every_table() -> None:
    await upgrade()
    await downgrade("base")
    assert await read_revision() is None
    for table in EXPECTED_TABLES:
        assert await table_exists(table) is False


async def test_upgrade_is_repeatable_after_downgrade() -> None:
    await upgrade()
    await downgrade("base")
    await upgrade()
    assert await read_revision() == EXPECTED_HEAD


async def test_single_step_downgrade_removes_only_the_latest_tables() -> None:
    await upgrade()
    await downgrade("-1")
    assert await read_revision() == "0008"
    # Phase 9's table is gone; earlier phases' remain.
    assert await table_exists("readiness_assessments") is False
    assert await table_exists("risk_findings") is True
    assert await table_exists("requirements") is True
    assert await table_exists("company_profiles") is True
    assert await table_exists("users") is True


async def test_downgrade_to_the_baseline_removes_the_auth_tables() -> None:
    await upgrade()
    await downgrade("0001")
    assert await read_revision() == "0001"
    assert await table_exists("users") is False


async def test_email_lowercase_check_constraint_is_enforced() -> None:
    """The invariant the application relies on is also the database's rule."""
    await upgrade()
    engine = create_engine(get_settings())
    try:
        async with engine.begin() as connection:
            with pytest.raises(Exception, match="ck_users_email_lowercase"):
                await connection.execute(
                    text(
                        "INSERT INTO users (id, email, password_hash, display_name, is_active) "
                        "VALUES (gen_random_uuid(), 'Mixed@Case.test', 'x', 'x', true)"
                    )
                )
    finally:
        await engine.dispose()
