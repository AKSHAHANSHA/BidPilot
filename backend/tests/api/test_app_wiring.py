"""The app factory's wiring is part of the contract: schema paths, docs gating, CORS."""

from __future__ import annotations

from fastapi import FastAPI
from httpx import AsyncClient

from app.core.config import Settings
from app.core.constants import REQUEST_ID_HEADER
from app.main import create_app


def test_openapi_documents_health_endpoints(app: FastAPI) -> None:
    paths = app.openapi()["paths"]
    assert "/api/v1/health/live" in paths
    assert "/api/v1/health/ready" in paths
    # The unprefixed platform aliases are functional but intentionally undocumented, so
    # each operation appears exactly once in the generated client.
    assert "/health/live" not in paths


def test_readiness_documents_its_503_problem_shape(app: FastAPI) -> None:
    responses = app.openapi()["paths"]["/api/v1/health/ready"]["get"]["responses"]
    assert "503" in responses


def test_docs_are_served_outside_production(app: FastAPI) -> None:
    assert app.docs_url == "/docs"
    assert app.openapi_url == "/openapi.json"


def test_docs_are_disabled_in_production(settings: Settings) -> None:
    production = create_app(settings.model_copy(update={"app_env": "production"}))
    assert production.docs_url is None
    assert production.openapi_url is None


async def test_cors_allows_the_configured_frontend_origin(client: AsyncClient) -> None:
    origin = "http://localhost:5173"
    response = await client.get("/api/v1/health/live", headers={"Origin": origin})
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"
    # The frontend must be able to read the correlation ID to show it in an error state.
    assert REQUEST_ID_HEADER.lower() in response.headers["access-control-expose-headers"].lower()


async def test_cors_rejects_an_unlisted_origin(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/health/live", headers={"Origin": "https://attacker.example"}
    )
    assert "access-control-allow-origin" not in response.headers
