"""Phase 8: evidence matching against company evidence, and risk extraction + review."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.integration.conftest import ProviderHolder
from tests.integration.factories import (
    make_pdf,
    scripted_extraction,
    valid_evidence_payload,
    valid_profile_payload,
)
from tests.integration.test_company_api import Signed, sign_up
from tests.integration.test_tender_api import create_tender, pdf_upload

pytestmark = pytest.mark.integration

DOC = make_pdf(
    "The bidder shall hold a valid UAE trade licence and maintain ISO 9001 certification.",
    "Liquidated damages of one percent per week of delay shall apply.",
)


@pytest.fixture(autouse=True)
def _mock_provider(provider_holder: ProviderHolder) -> None:
    provider_holder.provider = scripted_extraction(requirement_count=12)


async def _setup_with_evidence(client: AsyncClient, actor: Signed) -> str:
    """Create a profile with a verified ISO 9001 certification, then run an analysis."""
    await client.post("/api/v1/company", json=valid_profile_payload(), headers=actor.headers)
    await client.post(
        "/api/v1/company/evidence",
        json=valid_evidence_payload(
            title="ISO 9001 Quality Certificate",
            category="certification",
            verification_status="verified",
            tags=["iso", "9001"],
        ),
        headers=actor.headers,
    )
    tender_id = await create_tender(client, actor)
    await client.post(
        f"/api/v1/tenders/{tender_id}/documents",
        files=pdf_upload(content=DOC),
        headers=actor.headers,
    )
    created = await client.post(f"/api/v1/tenders/{tender_id}/analyses", headers=actor.headers)
    assert created.status_code == 202, created.text
    assert created.json()["status"] == "completed"
    return created.json()["id"]


async def test_requirements_get_a_machine_status_from_matching(client: AsyncClient) -> None:
    actor = await sign_up(client)
    analysis_id = await _setup_with_evidence(client, actor)

    listing = await client.get(
        f"/api/v1/analyses/{analysis_id}/requirements?limit=100", headers=actor.headers
    )
    statuses = {r["machine_status"] for r in listing.json()["items"]}
    # Matching ran: certification requirements meet the verified ISO evidence; others are
    # not_met/not_applicable — but nothing is left "unreviewed".
    assert "unreviewed" not in statuses
    assert "met" in statuses


async def test_certification_requirement_matches_verified_evidence(client: AsyncClient) -> None:
    actor = await sign_up(client)
    analysis_id = await _setup_with_evidence(client, actor)
    certs = await client.get(
        f"/api/v1/analyses/{analysis_id}/requirements?category=certification",
        headers=actor.headers,
    )
    assert any(r["machine_status"] == "met" for r in certs.json()["items"])


async def test_missing_evidence_is_not_met(client: AsyncClient) -> None:
    """With no company profile, matched requirements are not_met (never proven-absent)."""
    actor = await sign_up(client)
    tender_id = await create_tender(client, actor)
    await client.post(
        f"/api/v1/tenders/{tender_id}/documents",
        files=pdf_upload(content=DOC),
        headers=actor.headers,
    )
    created = await client.post(f"/api/v1/tenders/{tender_id}/analyses", headers=actor.headers)
    analysis_id = created.json()["id"]
    certs = await client.get(
        f"/api/v1/analyses/{analysis_id}/requirements?category=certification",
        headers=actor.headers,
    )
    assert all(r["machine_status"] == "not_met" for r in certs.json()["items"])


# --- Risks ---------------------------------------------------------------------------------


async def test_risks_are_extracted_and_citation_verified(client: AsyncClient) -> None:
    actor = await sign_up(client)
    analysis_id = await _setup_with_evidence(client, actor)
    risks = await client.get(f"/api/v1/analyses/{analysis_id}/risks", headers=actor.headers)
    assert risks.status_code == 200
    items = risks.json()
    assert len(items) == 2  # one verifiable, one hallucinated

    verified = [r for r in items if r["citation_verified"]]
    rejected = [r for r in items if not r["citation_verified"]]
    assert len(verified) == 1
    assert len(rejected) == 1
    assert verified[0]["risk_type"] == "liquidated_damages"
    assert verified[0]["citations"][0]["verified"] is True
    assert rejected[0]["citations"][0]["match_method"] == "rejected"
    # Advisory language, no legal conclusions.
    assert "review" in verified[0]["suggested_action"].lower()


async def test_risks_sorted_most_severe_first(client: AsyncClient) -> None:
    actor = await sign_up(client)
    analysis_id = await _setup_with_evidence(client, actor)
    risks = await client.get(f"/api/v1/analyses/{analysis_id}/risks", headers=actor.headers)
    severities = [r["severity"] for r in risks.json()]
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    assert severities == sorted(severities, key=lambda s: order[s])


# --- Human review --------------------------------------------------------------------------


async def test_requirement_review_requires_a_reason(client: AsyncClient) -> None:
    actor = await sign_up(client)
    analysis_id = await _setup_with_evidence(client, actor)
    req_id = (
        await client.get(f"/api/v1/analyses/{analysis_id}/requirements", headers=actor.headers)
    ).json()["items"][0]["id"]

    no_reason = await client.patch(
        f"/api/v1/requirements/{req_id}/review",
        json={"reviewed_status": "met"},
        headers=actor.headers,
    )
    assert no_reason.status_code == 422


async def test_requirement_review_preserves_machine_status(client: AsyncClient) -> None:
    actor = await sign_up(client)
    analysis_id = await _setup_with_evidence(client, actor)
    listing = await client.get(
        f"/api/v1/analyses/{analysis_id}/requirements", headers=actor.headers
    )
    req = listing.json()["items"][0]
    original_machine = req["machine_status"]

    reviewed = await client.patch(
        f"/api/v1/requirements/{req['id']}/review",
        json={"reviewed_status": "not_applicable", "reason": "Handled by our parent company."},
        headers=actor.headers,
    )
    assert reviewed.status_code == 200
    body = reviewed.json()
    assert body["reviewed_status"] == "not_applicable"
    assert body["review_reason"] == "Handled by our parent company."
    # The machine's original verdict is preserved.
    assert body["machine_status"] == original_machine


async def test_risk_review_records_reason(client: AsyncClient) -> None:
    actor = await sign_up(client)
    analysis_id = await _setup_with_evidence(client, actor)
    risk_id = (
        await client.get(f"/api/v1/analyses/{analysis_id}/risks", headers=actor.headers)
    ).json()[0]["id"]

    reviewed = await client.patch(
        f"/api/v1/risks/{risk_id}/review",
        json={"reviewed_status": "needs_clarification", "reason": "Legal to confirm the cap."},
        headers=actor.headers,
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["reviewed_status"] == "needs_clarification"


# --- Ownership -----------------------------------------------------------------------------


async def test_risks_and_reviews_are_ownership_isolated(client: AsyncClient) -> None:
    alice = await sign_up(client, "alice")
    bob = await sign_up(client, "bob")
    analysis_id = await _setup_with_evidence(client, alice)
    risk_id = (
        await client.get(f"/api/v1/analyses/{analysis_id}/risks", headers=alice.headers)
    ).json()[0]["id"]

    assert (
        await client.get(f"/api/v1/analyses/{analysis_id}/risks", headers=bob.headers)
    ).status_code == 404
    assert (
        await client.patch(
            f"/api/v1/risks/{risk_id}/review",
            json={"reviewed_status": "met", "reason": "attempted hijack"},
            headers=bob.headers,
        )
    ).status_code == 404


async def test_unknown_risk_review_is_404(client: AsyncClient) -> None:
    actor = await sign_up(client)
    assert (
        await client.patch(
            f"/api/v1/risks/{uuid.uuid4()}/review",
            json={"reviewed_status": "met", "reason": "nope"},
            headers=actor.headers,
        )
    ).status_code == 404
