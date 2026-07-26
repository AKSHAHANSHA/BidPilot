"""Readiness against the real containers — the probe the deployment platform will use."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.database import check_database
from app.core.redis_client import check_redis

pytestmark = pytest.mark.integration


async def test_database_is_reachable() -> None:
    await check_database()


async def test_redis_is_reachable() -> None:
    await check_redis()


async def test_readiness_reports_every_dependency_ok(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health/ready")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ready"
    assert {dep["name"]: dep["status"] for dep in body["dependencies"]} == {
        "database": "ok",
        "redis": "ok",
    }
