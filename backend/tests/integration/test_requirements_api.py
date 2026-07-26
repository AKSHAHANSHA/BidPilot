"""Requirement extraction end to end (mocked provider) and the requirements read API.

Phase 6 exit test: at least ten structured requirements are extracted and persisted with
citations from a sample tender.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.integration.conftest import ProviderHolder
from tests.integration.factories import make_pdf, scripted_extraction
from tests.integration.test_company_api import sign_up
from tests.integration.test_tender_api import create_tender, pdf_upload

pytestmark = pytest.mark.integration

DOC = make_pdf(
    "The bidder shall hold a valid UAE trade licence and maintain ISO 9001 certification.",
    "Liquidated damages of one percent per week of delay shall apply.",
)


@pytest.fixture(autouse=True)
def _mock_provider(provider_holder: ProviderHolder) -> None:
    provider_holder.provider = scripted_extraction(requirement_count=12)


async def run_analysis(client: AsyncClient, headers: dict[str, str]) -> str:
    tender_id = await create_tender(client, type("A", (), {"headers": headers})())  # type: ignore[arg-type]
    await client.post(
        f"/api/v1/tenders/{tender_id}/documents", files=pdf_upload(content=DOC), headers=headers
    )
    created = await client.post(f"/api/v1/tenders/{tender_id}/analyses", headers=headers)
    assert created.status_code == 202, created.text
    assert created.json()["status"] == "completed"
    return created.json()["id"]


async def test_at_least_ten_requirements_are_extracted(client: AsyncClient) -> None:
    actor = await sign_up(client)
    analysis_id = await run_analysis(client, actor.headers)

    listing = await client.get(
        f"/api/v1/analyses/{analysis_id}/requirements?limit=100", headers=actor.headers
    )
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] >= 10
    first = body["items"][0]
    assert first["original_text"]
    assert first["category"]
    assert first["obligation"] in {"mandatory", "optional", "uncertain"}
    # Citations are persisted with a real source page. The pipeline includes Phase 7
    # verification, and these quotes are verbatim from the pages, so they verify.
    assert first["citations"]
    assert first["citations"][0]["page_number"] >= 1
    assert first["citation_verified"] is True
    assert first["citations"][0]["verified"] is True
    assert first["citations"][0]["match_method"] in {"exact", "normalized", "fuzzy"}


async def test_token_and_cost_are_recorded(client: AsyncClient) -> None:
    actor = await sign_up(client)
    analysis_id = await run_analysis(client, actor.headers)
    analysis = await client.get(f"/api/v1/analyses/{analysis_id}", headers=actor.headers)
    body = analysis.json()
    assert body["input_tokens"] > 0
    assert body["output_tokens"] > 0
    assert float(body["estimated_cost"]) >= 0
    assert body["provider"] == "mock"


async def test_requirement_filters(client: AsyncClient) -> None:
    actor = await sign_up(client)
    analysis_id = await run_analysis(client, actor.headers)

    async def total(params: str) -> int:
        r = await client.get(
            f"/api/v1/analyses/{analysis_id}/requirements?{params}", headers=actor.headers
        )
        assert r.status_code == 200, r.text
        return r.json()["total"]

    assert await total("category=certification") >= 1
    assert await total("obligation=mandatory") >= 1
    # All fixture quotes are verbatim from their cited pages, so all verify.
    assert await total("citation_verified=true") >= 10
    assert await total("citation_verified=false") == 0


async def test_get_single_requirement_with_citations(client: AsyncClient) -> None:
    actor = await sign_up(client)
    analysis_id = await run_analysis(client, actor.headers)
    listing = await client.get(
        f"/api/v1/analyses/{analysis_id}/requirements", headers=actor.headers
    )
    req_id = listing.json()["items"][0]["id"]

    single = await client.get(f"/api/v1/requirements/{req_id}", headers=actor.headers)
    assert single.status_code == 200
    assert single.json()["id"] == req_id
    assert single.json()["citations"]


async def test_requirements_are_ownership_isolated(client: AsyncClient) -> None:
    alice = await sign_up(client, "alice")
    bob = await sign_up(client, "bob")
    analysis_id = await run_analysis(client, alice.headers)
    listing = await client.get(
        f"/api/v1/analyses/{analysis_id}/requirements", headers=alice.headers
    )
    req_id = listing.json()["items"][0]["id"]

    assert (
        await client.get(f"/api/v1/analyses/{analysis_id}/requirements", headers=bob.headers)
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/requirements/{req_id}", headers=bob.headers)
    ).status_code == 404


async def test_ai_failure_marks_the_analysis_failed(
    client: AsyncClient, provider_holder: ProviderHolder
) -> None:
    """A provider error during extraction fails the analysis with a safe code, retryable."""
    from app.ai.providers.base import LLMProviderError
    from app.ai.providers.mock import MockLLMProvider, ScriptedResponse
    from tests.integration.factories import metadata_json

    # Metadata succeeds, then requirements fail on both the initial call and the retry.
    provider_holder.provider = MockLLMProvider(
        [
            ScriptedResponse(metadata_json()),
            ScriptedResponse(error=LLMProviderError("boom")),
            ScriptedResponse(error=LLMProviderError("boom")),
        ]
    )
    actor = await sign_up(client)
    tender_id = await create_tender(client, actor)
    await client.post(
        f"/api/v1/tenders/{tender_id}/documents",
        files=pdf_upload(content=DOC),
        headers=actor.headers,
    )
    created = await client.post(f"/api/v1/tenders/{tender_id}/analyses", headers=actor.headers)
    body = created.json()
    assert body["status"] == "failed"
    assert body["error_code"] == "failed_ai"
    assert body["can_retry"] is True
    # No requirements were persisted from the failed run.
    listing = await client.get(f"/api/v1/analyses/{body['id']}/requirements", headers=actor.headers)
    assert listing.json()["total"] == 0


async def test_unknown_analysis_requirements_is_404(client: AsyncClient) -> None:
    actor = await sign_up(client)
    assert (
        await client.get(f"/api/v1/analyses/{uuid.uuid4()}/requirements", headers=actor.headers)
    ).status_code == 404
