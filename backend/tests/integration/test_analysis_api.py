"""Analysis lifecycle: queue, process, retry, idempotency, and ownership.

The eager job queue (see conftest) runs the pipeline inline, so a queued analysis reaches its
terminal state within the request. The real Dramatiq worker is exercised by the live smoke
test, not the suite — the suite must not depend on a running broker.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import Analysis
from tests.integration.factories import make_pdf
from tests.integration.test_company_api import Signed, sign_up
from tests.integration.test_tender_api import create_tender, pdf_upload

pytestmark = pytest.mark.integration

DOC = make_pdf(
    "The bidder shall hold a valid UAE trade licence and maintain ISO 9001 certification "
    "for the full duration of the contract as set out in the particular conditions.",
    "Liquidated damages of one percent per week of delay shall apply, capped at ten percent "
    "of the total contract value stated in the commercial schedule.",
)


async def tender_with_document(client: AsyncClient, actor: Signed, content: bytes = DOC) -> str:
    tender_id = await create_tender(client, actor)
    upload = await client.post(
        f"/api/v1/tenders/{tender_id}/documents",
        files=pdf_upload(content=content),
        headers=actor.headers,
    )
    assert upload.status_code == 201, upload.text
    return tender_id


async def test_analysis_runs_to_completion(client: AsyncClient) -> None:
    actor = await sign_up(client)
    tender_id = await tender_with_document(client, actor)

    response = await client.post(f"/api/v1/tenders/{tender_id}/analyses", headers=actor.headers)
    assert response.status_code == 202, response.text
    body = response.json()
    # The eager queue has already driven the pipeline to completion.
    assert body["status"] == "completed"
    assert body["current_stage"] == "completed"
    assert body["version"] == 1
    assert body["attempt_count"] == 1
    assert body["started_at"] is not None
    assert body["completed_at"] is not None
    assert body["prompt_version"]
    assert body["summary"] is not None
    assert body["can_retry"] is False


async def test_analysis_requires_a_document(client: AsyncClient) -> None:
    actor = await sign_up(client)
    tender_id = await create_tender(client, actor)
    response = await client.post(f"/api/v1/tenders/{tender_id}/analyses", headers=actor.headers)
    assert response.status_code == 422
    assert "document" in response.json()["detail"].lower()


async def test_unsupported_document_cannot_be_analysed(client: AsyncClient) -> None:
    actor = await sign_up(client)
    tender_id = await tender_with_document(client, actor, content=make_pdf("", "", ""))
    response = await client.post(f"/api/v1/tenders/{tender_id}/analyses", headers=actor.headers)
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_INVALID"


async def test_events_endpoint_reports_terminal_state(client: AsyncClient) -> None:
    actor = await sign_up(client)
    tender_id = await tender_with_document(client, actor)
    created = await client.post(f"/api/v1/tenders/{tender_id}/analyses", headers=actor.headers)
    analysis_id = created.json()["id"]

    event = await client.get(f"/api/v1/analyses/{analysis_id}/events", headers=actor.headers)
    assert event.status_code == 200
    body = event.json()
    assert body["status"] == "completed"
    assert body["current_stage"] == "completed"
    # The progress payload is compact: status and stage, no fabricated percentage.
    assert "percent" not in body
    assert "progress" not in body


async def test_second_analysis_creates_a_new_version(client: AsyncClient) -> None:
    actor = await sign_up(client)
    tender_id = await tender_with_document(client, actor)

    first = await client.post(f"/api/v1/tenders/{tender_id}/analyses", headers=actor.headers)
    assert first.json()["version"] == 1
    # First run completed (eager), so a second call starts a fresh version.
    second = await client.post(f"/api/v1/tenders/{tender_id}/analyses", headers=actor.headers)
    assert second.status_code == 202
    assert second.json()["version"] == 2

    listing = await client.get(f"/api/v1/tenders/{tender_id}/analyses", headers=actor.headers)
    assert [a["version"] for a in listing.json()] == [2, 1]


async def test_retry_only_applies_to_failed_analyses(client: AsyncClient) -> None:
    actor = await sign_up(client)
    tender_id = await tender_with_document(client, actor)
    created = await client.post(f"/api/v1/tenders/{tender_id}/analyses", headers=actor.headers)
    analysis_id = created.json()["id"]
    # A completed analysis cannot be retried.
    retry = await client.post(f"/api/v1/analyses/{analysis_id}/retry", headers=actor.headers)
    assert retry.status_code == 409


async def test_failed_analysis_can_be_retried(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    actor = await sign_up(client)
    tender_id = await tender_with_document(client, actor)
    created = await client.post(f"/api/v1/tenders/{tender_id}/analyses", headers=actor.headers)
    analysis_id = created.json()["id"]

    # Force the completed run into a failed state to exercise retry deterministically, without
    # needing to induce a real pipeline failure.
    await db_session.execute(
        update(Analysis)
        .where(Analysis.id == uuid.UUID(analysis_id))
        .values(status="failed", error_code="failed_ai", completed_at=None)
    )
    await db_session.commit()

    retry = await client.post(f"/api/v1/analyses/{analysis_id}/retry", headers=actor.headers)
    assert retry.status_code == 202
    # The eager queue re-ran the pipeline, so it is completed again.
    assert retry.json()["status"] == "completed"
    assert retry.json()["attempt_count"] == 2


# --- Ownership -----------------------------------------------------------------------------


async def test_analyses_are_ownership_isolated(client: AsyncClient) -> None:
    alice = await sign_up(client, "alice")
    bob = await sign_up(client, "bob")
    tender_id = await tender_with_document(client, alice)
    created = await client.post(f"/api/v1/tenders/{tender_id}/analyses", headers=alice.headers)
    analysis_id = created.json()["id"]

    assert (
        await client.get(f"/api/v1/analyses/{analysis_id}", headers=bob.headers)
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/analyses/{analysis_id}/events", headers=bob.headers)
    ).status_code == 404
    assert (
        await client.post(f"/api/v1/analyses/{analysis_id}/retry", headers=bob.headers)
    ).status_code == 404
    assert (
        await client.post(f"/api/v1/tenders/{tender_id}/analyses", headers=bob.headers)
    ).status_code == 404


async def test_analysis_requires_authentication(client: AsyncClient) -> None:
    assert (await client.post(f"/api/v1/tenders/{uuid.uuid4()}/analyses")).status_code == 401
    assert (await client.get(f"/api/v1/analyses/{uuid.uuid4()}")).status_code == 401


async def test_deleting_the_tender_removes_its_analyses(client: AsyncClient) -> None:
    actor = await sign_up(client)
    tender_id = await tender_with_document(client, actor)
    created = await client.post(f"/api/v1/tenders/{tender_id}/analyses", headers=actor.headers)
    analysis_id = created.json()["id"]
    assert (
        await client.delete(f"/api/v1/tenders/{tender_id}", headers=actor.headers)
    ).status_code == 204
    assert (
        await client.get(f"/api/v1/analyses/{analysis_id}", headers=actor.headers)
    ).status_code == 404
