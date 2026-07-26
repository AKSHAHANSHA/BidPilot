"""Every client-visible failure is an RFC 7807 problem document — and nothing more.

The privacy assertions here matter as much as the shape assertions: a 500 must not carry a
traceback or an exception message, and a validation error must not echo the rejected value
back to the caller.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from app.api.errors import ConflictError, NotFoundError, ValidationProblem
from app.core.config import Settings
from app.core.constants import PROBLEM_JSON_MEDIA_TYPE, REQUEST_ID_HEADER
from app.main import create_app

LEAKY_MESSAGE = "asyncpg cannot connect: user=bidpilot password=hunter2 host=db"


class Credentials(BaseModel):
    email: str
    password: str


@pytest.fixture
def error_app(settings: Settings) -> FastAPI:
    """An app with routes that fail in each way the contract must cover."""
    app = create_app(settings)

    @app.get("/probe/not-found")
    async def not_found() -> None:
        raise NotFoundError("The requested tender does not exist.")

    @app.get("/probe/conflict")
    async def conflict() -> None:
        raise ConflictError("A document with this SHA-256 already exists on this tender.")

    @app.get("/probe/invalid")
    async def invalid() -> None:
        raise ValidationProblem("Submission deadline must be in the future.")

    @app.get("/probe/unexpected")
    async def unexpected() -> None:
        raise RuntimeError(LEAKY_MESSAGE)

    @app.post("/probe/credentials")
    async def credentials(payload: Credentials) -> dict[str, str]:
        return {"email": payload.email}

    return app


@pytest.fixture
async def error_client(error_app: FastAPI):
    transport = ASGITransport(app=error_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client


def assert_problem(body: dict[str, object], *, status: int, code: str) -> None:
    assert body["status"] == status
    assert body["code"] == code
    assert str(body["type"]).startswith("https://bidpilot.dev/problems/")
    assert body["title"]
    assert body["detail"]
    assert body["request_id"]


async def test_unknown_route_returns_problem_details(error_client: AsyncClient) -> None:
    response = await error_client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith(PROBLEM_JSON_MEDIA_TYPE)
    assert_problem(response.json(), status=404, code="HTTP_404")


async def test_app_error_maps_to_declared_status_and_code(error_client: AsyncClient) -> None:
    response = await error_client.get("/probe/not-found")
    assert response.status_code == 404
    body = response.json()
    assert_problem(body, status=404, code="RESOURCE_NOT_FOUND")
    assert body["instance"] == "/probe/not-found"


@pytest.mark.parametrize(
    ("path", "status", "code"),
    [
        ("/probe/conflict", 409, "RESOURCE_CONFLICT"),
        ("/probe/invalid", 422, "REQUEST_INVALID"),
    ],
)
async def test_error_subclasses(
    error_client: AsyncClient, path: str, status: int, code: str
) -> None:
    response = await error_client.get(path)
    assert response.status_code == status
    assert_problem(response.json(), status=status, code=code)


async def test_validation_failure_reports_fields(error_client: AsyncClient) -> None:
    response = await error_client.post("/probe/credentials", json={"email": "a@b.test"})
    assert response.status_code == 422
    body = response.json()
    assert_problem(body, status=422, code="REQUEST_VALIDATION_FAILED")
    fields = {error["field"] for error in body["errors"]}
    assert "body.password" in fields


async def test_validation_failure_does_not_echo_submitted_value(
    error_client: AsyncClient,
) -> None:
    # A rejected password must not come back in the response body or the caller's logs.
    response = await error_client.post(
        "/probe/credentials", json={"email": "a@b.test", "password": 12345}
    )
    assert response.status_code == 422
    assert "12345" not in response.text


async def test_unexpected_error_is_contained(error_client: AsyncClient) -> None:
    response = await error_client.get("/probe/unexpected")
    assert response.status_code == 500
    assert response.headers["content-type"].startswith(PROBLEM_JSON_MEDIA_TYPE)
    assert_problem(response.json(), status=500, code="INTERNAL_ERROR")


async def test_unexpected_error_leaks_neither_traceback_nor_message(
    error_client: AsyncClient,
) -> None:
    response = await error_client.get("/probe/unexpected")
    text = response.text
    assert "hunter2" not in text
    assert "asyncpg" not in text
    assert "Traceback" not in text
    assert "RuntimeError" not in text


async def test_request_id_is_generated_and_echoed(error_client: AsyncClient) -> None:
    response = await error_client.get("/api/v1/health/live")
    assert response.headers[REQUEST_ID_HEADER]


async def test_supplied_request_id_is_preserved_end_to_end(error_client: AsyncClient) -> None:
    response = await error_client.get(
        "/probe/not-found", headers={REQUEST_ID_HEADER: "demo-request-1"}
    )
    assert response.headers[REQUEST_ID_HEADER] == "demo-request-1"
    assert response.json()["request_id"] == "demo-request-1"


async def test_request_id_present_on_contained_500(error_client: AsyncClient) -> None:
    response = await error_client.get(
        "/probe/unexpected", headers={REQUEST_ID_HEADER: "trace-me-500"}
    )
    assert response.headers[REQUEST_ID_HEADER] == "trace-me-500"
    assert response.json()["request_id"] == "trace-me-500"


async def test_hostile_request_id_is_not_reflected(error_client: AsyncClient) -> None:
    response = await error_client.get(
        "/api/v1/health/live", headers={REQUEST_ID_HEADER: "<script>alert(1)</script>"}
    )
    assert "<script>" not in response.headers[REQUEST_ID_HEADER]
