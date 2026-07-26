"""Shared test configuration.

Environment variables are set at import time, before anything imports `app.core.config`, so
the test suite never inherits a developer's `.env` — in particular it can never point at a
real database or a real provider key.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

TEST_UPLOAD_DIR = Path(tempfile.gettempdir()) / "bidpilot-test-uploads"

os.environ.update(
    {
        "APP_ENV": "test",
        "LOG_LEVEL": "WARNING",
        "JWT_SECRET": "test-only-jwt-secret-value-0123456789abcdef",
        # Ports match docker-compose.yml. A dedicated database keeps integration tests from
        # dropping the schema out from under seeded demo data in `bidpilot`.
        "DATABASE_URL": ("postgresql+asyncpg://bidpilot:bidpilot@localhost:55432/bidpilot_test"),
        "REDIS_URL": "redis://localhost:56379/1",
        "UPLOAD_DIR": str(TEST_UPLOAD_DIR),
        "OPENAI_API_KEY": "",
        "OPENAI_MODEL": "",
        "ANTHROPIC_API_KEY": "",
        "ANTHROPIC_MODEL": "",
    }
)

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core.config import Settings, get_settings  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture
def settings() -> Iterator[Settings]:
    """Fresh, cache-isolated settings built from the test environment."""
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """HTTP client speaking directly to the ASGI app — no socket, no live server."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client
