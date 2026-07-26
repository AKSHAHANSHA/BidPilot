"""Liveness must not depend on anything; readiness must report what is broken."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.constants import PROBLEM_JSON_MEDIA_TYPE


async def _ok() -> None:
    return None


async def _fail() -> None:
    raise ConnectionRefusedError("connect to bidpilot:hunter2@db:5432 refused")


@pytest.fixture(autouse=True)
def healthy_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default to reachable dependencies so no unit-level test opens a socket."""
    monkeypatch.setattr("app.api.v1.health.check_database", _ok)
    monkeypatch.setattr("app.api.v1.health.check_redis", _ok)


async def test_liveness_returns_live(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "live"}


async def test_liveness_ignores_broken_dependencies(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A database outage must not make the process look dead; that causes restart loops.
    monkeypatch.setattr("app.api.v1.health.check_database", _fail)
    monkeypatch.setattr("app.api.v1.health.check_redis", _fail)
    response = await client.get("/api/v1/health/live")
    assert response.status_code == 200


async def test_liveness_available_on_unprefixed_alias(client: AsyncClient) -> None:
    # Hosting platforms probe a fixed path regardless of API_V1_PREFIX.
    assert (await client.get("/health/live")).status_code == 200


async def test_readiness_ok_when_dependencies_reachable(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert {dep["name"]: dep["status"] for dep in body["dependencies"]} == {
        "database": "ok",
        "redis": "ok",
    }


async def test_readiness_503_when_database_unavailable(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.api.v1.health.check_database", _fail)
    response = await client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.headers["content-type"].startswith(PROBLEM_JSON_MEDIA_TYPE)
    body = response.json()
    assert body["code"] == "SERVICE_DEPENDENCY_UNAVAILABLE"
    assert "database" in body["detail"]
    assert body["request_id"]
    assert body["instance"] == "/api/v1/health/ready"


async def test_readiness_503_when_redis_unavailable(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.api.v1.health.check_redis", _fail)
    response = await client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert "redis" in response.json()["detail"]


async def test_readiness_does_not_leak_connection_details(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.api.v1.health.check_database", _fail)
    response = await client.get("/api/v1/health/ready")
    assert "hunter2" not in response.text
    assert "5432" not in response.text
