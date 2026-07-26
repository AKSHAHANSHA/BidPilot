"""Integration-test scaffolding.

These tests talk to the PostgreSQL and Redis containers from `docker-compose.yml`.

Isolation strategy: the schema is migrated once per session, then every test runs inside a
transaction that is rolled back afterwards. The session is joined to that transaction with
`join_transaction_mode="create_savepoint"`, so a `commit()` in the application code releases a
savepoint rather than committing — the code under test sees real commit semantics, and no test
leaves residue for the next one.

Each async test also runs in its own event loop, so cached connection pools are disposed
between tests; a pool bound to a closed loop would fail unpredictably later.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.database import create_engine, dispose_engine, get_session
from app.core.rate_limit import KEY_PREFIX
from app.core.redis_client import close_redis, get_redis
from app.main import create_app

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def alembic_config() -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    # Make the run independent of the working directory pytest was invoked from.
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    return config


@pytest.fixture(scope="session")
def migrated_database() -> None:
    """Bring the test database to head once per session.

    Synchronous on purpose: `migrations/env.py` calls `asyncio.run(...)`, which cannot be
    nested inside a running event loop.
    """
    config = alembic_config()
    command.downgrade(config, "base")
    command.upgrade(config, "head")


@pytest.fixture
async def db_session(migrated_database: None) -> AsyncIterator[AsyncSession]:
    """A session inside a transaction that is always rolled back."""
    engine = create_engine(get_settings())
    connection = await engine.connect()
    transaction = await connection.begin()
    factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )
    session = factory()
    try:
        yield session
    finally:
        await session.close()
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()
        await engine.dispose()


@pytest.fixture
def app(settings: Settings, db_session: AsyncSession) -> FastAPI:
    """The real application, with the request session replaced by the test transaction."""
    application = create_app(settings)

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        # Mirrors `app.core.database.get_session` exactly, including the rollback on error.
        # An override that only committed on success would let writes made before an exception
        # survive inside the test session — which silently hid a real bug where a
        # refresh-token revocation was rolled back by the very error that triggered it.
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    application.dependency_overrides[get_session] = override_get_session

    # Run the analysis pipeline inline against the test session instead of enqueuing to Redis,
    # so the full journey (queue → process → complete) can be asserted without a live worker.
    from app.api.dependencies import get_job_queue
    from app.workers.queue import EagerJobQueue

    application.dependency_overrides[get_job_queue] = lambda: EagerJobQueue(db_session)
    return application


@pytest.fixture(autouse=True)
async def _clear_rate_limit_buckets() -> AsyncIterator[None]:
    """Rate-limit counters live in Redis and would otherwise leak across tests."""
    redis = get_redis()
    keys = [key async for key in redis.scan_iter(match=f"{KEY_PREFIX}:*")]
    if keys:
        await redis.delete(*keys)
    yield


@pytest.fixture(autouse=True)
async def _release_connection_pools() -> AsyncIterator[None]:
    yield
    await dispose_engine()
    await close_redis()
