"""Phase 7 exit test: no canonical requirement carries an invalid citation.

Uses the mocked provider, but the quotes it returns are real phrases from the uploaded pages
(and one deliberately hallucinated quote), so verification does genuine text matching.
"""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient

from tests.integration.conftest import ProviderHolder
from tests.integration.factories import make_pdf, metadata_json
from tests.integration.test_company_api import sign_up
from tests.integration.test_tender_api import create_tender, pdf_upload

pytestmark = pytest.mark.integration

PAGE_ONE = (
    "Section 1. The bidder shall hold a valid UAE trade licence covering the required "
    "facilities management activities for the full contract period."
)
PAGE_TWO = (
    "Section 2. Liquidated damages of one percent per week of delay shall apply, capped at "
    "ten percent of the total contract value."
)
DOC = make_pdf(PAGE_ONE, PAGE_TWO)


def requirements_with_mixed_citations() -> str:
    """Two verifiable requirements (real quotes) and one hallucinated (bogus quote)."""
    return json.dumps(
        {
            "requirements": [
                {
                    "original_text": "Valid UAE trade licence required.",
                    "normalized_text": "Hold a valid UAE trade licence.",
                    "category": "legal_registration",
                    "obligation": "mandatory",
                    "expected_evidence": ["trade licence"],
                    "source_page": 1,
                    "source_quote": "The bidder shall hold a valid UAE trade licence",
                    "confidence": 0.95,
                },
                {
                    "original_text": "Liquidated damages apply.",
                    "normalized_text": "Accept liquidated damages for delay.",
                    "category": "contractual",
                    "obligation": "mandatory",
                    "expected_evidence": [],
                    "source_page": 2,
                    "source_quote": "Liquidated damages of one percent per week of delay",
                    "confidence": 0.9,
                },
                {
                    "original_text": "Fabricated requirement.",
                    "normalized_text": "A requirement the document does not contain.",
                    "category": "certification",
                    "obligation": "mandatory",
                    "expected_evidence": [],
                    "source_page": 1,
                    # This quote is not on page 1 — verification must reject it.
                    "source_quote": "The bidder must hold a platinum safety accreditation grade",
                    "confidence": 0.8,
                },
            ]
        }
    )


@pytest.fixture(autouse=True)
def _mock_provider(provider_holder: ProviderHolder) -> None:
    from app.ai.providers.mock import RoutedMockProvider
    from tests.integration.factories import risk_batch_json

    provider_holder.provider = RoutedMockProvider(
        {
            "tender_metadata": metadata_json(),
            "requirement_batch": requirements_with_mixed_citations(),
            "risk_batch": risk_batch_json(),
        }
    )


async def _run(client: AsyncClient, headers: dict[str, str]) -> str:
    tender_id = await create_tender(client, type("A", (), {"headers": headers})())  # type: ignore[arg-type]
    await client.post(
        f"/api/v1/tenders/{tender_id}/documents", files=pdf_upload(content=DOC), headers=headers
    )
    created = await client.post(f"/api/v1/tenders/{tender_id}/analyses", headers=headers)
    assert created.status_code == 202, created.text
    assert created.json()["status"] == "completed"
    return created.json()["id"]


async def test_verified_and_rejected_citations_are_classified(client: AsyncClient) -> None:
    actor = await sign_up(client)
    analysis_id = await _run(client, actor.headers)

    listing = await client.get(
        f"/api/v1/analyses/{analysis_id}/requirements?limit=100", headers=actor.headers
    )
    items = listing.json()["items"]
    assert len(items) == 3

    by_verified = {r["citation_verified"] for r in items}
    assert by_verified == {True, False}  # some verified, some not

    for req in items:
        for citation in req["citations"]:
            if citation["verified"]:
                assert citation["match_method"] in {"exact", "normalized", "fuzzy"}
                assert citation["match_score"] is not None
            else:
                assert citation["match_method"] == "rejected"


async def test_no_canonical_requirement_has_an_invalid_citation(client: AsyncClient) -> None:
    """The core Phase 7 guarantee (`docs/03` targets: zero invalid canonical citations)."""
    actor = await sign_up(client)
    analysis_id = await _run(client, actor.headers)

    verified = await client.get(
        f"/api/v1/analyses/{analysis_id}/requirements?citation_verified=true&limit=100",
        headers=actor.headers,
    )
    canonical = verified.json()["items"]
    assert len(canonical) == 2  # the two real requirements; the hallucinated one is excluded
    for req in canonical:
        # Every canonical requirement has at least one genuinely verified citation.
        assert any(c["verified"] for c in req["citations"])


async def test_hallucinated_requirement_is_not_canonical(client: AsyncClient) -> None:
    actor = await sign_up(client)
    analysis_id = await _run(client, actor.headers)
    unverified = await client.get(
        f"/api/v1/analyses/{analysis_id}/requirements?citation_verified=false&limit=100",
        headers=actor.headers,
    )
    items = unverified.json()["items"]
    assert len(items) == 1
    assert items[0]["citations"][0]["match_method"] == "rejected"
