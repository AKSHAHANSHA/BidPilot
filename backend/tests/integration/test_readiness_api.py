"""Phase 9: readiness scoring end to end, plus human override.

Exit test: the same structured inputs always produce the same numerical score.
"""

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


async def _run(client: AsyncClient, actor: Signed, *, with_evidence: bool = True) -> str:
    if with_evidence:
        await client.post("/api/v1/company", json=valid_profile_payload(), headers=actor.headers)
        await client.post(
            "/api/v1/company/evidence",
            json=valid_evidence_payload(
                title="ISO 9001 Quality Certificate",
                category="certification",
                verification_status="verified",
                tags=["iso"],
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


async def test_readiness_is_produced_with_dimensions(client: AsyncClient) -> None:
    actor = await sign_up(client)
    analysis_id = await _run(client, actor)

    response = await client.get(f"/api/v1/analyses/{analysis_id}/readiness", headers=actor.headers)
    assert response.status_code == 200
    body = response.json()
    assert 0 <= float(body["overall_score"]) <= 100
    assert body["decision_label"] in {
        "strong_bid",
        "conditional_bid",
        "weak_bid",
        "do_not_bid",
        "insufficient_information",
    }
    assert len(body["dimensions"]) == 6
    assert sum(d["weight"] for d in body["dimensions"]) == 100
    assert body["calculation_version"]
    assert body["assumptions"]
    assert body["human_override"] is None


async def test_scoring_is_deterministic_across_runs(client: AsyncClient) -> None:
    """The same inputs → the same score, on two separate analysis versions."""
    actor = await sign_up(client)
    await client.post("/api/v1/company", json=valid_profile_payload(), headers=actor.headers)
    await client.post(
        "/api/v1/company/evidence",
        json=valid_evidence_payload(category="certification", verification_status="verified"),
        headers=actor.headers,
    )
    tender_id = await create_tender(client, actor)
    await client.post(
        f"/api/v1/tenders/{tender_id}/documents",
        files=pdf_upload(content=DOC),
        headers=actor.headers,
    )

    first = await client.post(f"/api/v1/tenders/{tender_id}/analyses", headers=actor.headers)
    second = await client.post(f"/api/v1/tenders/{tender_id}/analyses", headers=actor.headers)

    r1 = await client.get(f"/api/v1/analyses/{first.json()['id']}/readiness", headers=actor.headers)
    r2 = await client.get(
        f"/api/v1/analyses/{second.json()['id']}/readiness", headers=actor.headers
    )
    assert r1.json()["overall_score"] == r2.json()["overall_score"]
    assert r1.json()["decision_label"] == r2.json()["decision_label"]


async def test_report_summary_reflects_the_score(client: AsyncClient) -> None:
    actor = await sign_up(client)
    analysis_id = await _run(client, actor)
    analysis = await client.get(f"/api/v1/analyses/{analysis_id}", headers=actor.headers)
    summary = analysis.json()["summary"]
    assert "Recommendation" in summary
    assert "readiness" in summary.lower()


# --- Human override ------------------------------------------------------------------------


async def test_override_requires_a_reason(client: AsyncClient) -> None:
    actor = await sign_up(client)
    analysis_id = await _run(client, actor)
    response = await client.patch(
        f"/api/v1/analyses/{analysis_id}/readiness/override",
        json={"decision_label": "do_not_bid"},
        headers=actor.headers,
    )
    assert response.status_code == 422


async def test_override_preserves_the_machine_result(client: AsyncClient) -> None:
    actor = await sign_up(client)
    analysis_id = await _run(client, actor)
    before = (
        await client.get(f"/api/v1/analyses/{analysis_id}/readiness", headers=actor.headers)
    ).json()

    response = await client.patch(
        f"/api/v1/analyses/{analysis_id}/readiness/override",
        json={"decision_label": "do_not_bid", "reason": "Board declined on strategic grounds."},
        headers=actor.headers,
    )
    assert response.status_code == 200
    body = response.json()
    # The machine score and label are unchanged; only the override is recorded.
    assert body["overall_score"] == before["overall_score"]
    assert body["decision_label"] == before["decision_label"]
    assert body["human_override"]["label"] == "do_not_bid"
    assert body["human_override"]["reason"] == "Board declined on strategic grounds."


# --- Ownership -----------------------------------------------------------------------------


async def test_readiness_is_ownership_isolated(client: AsyncClient) -> None:
    alice = await sign_up(client, "alice")
    bob = await sign_up(client, "bob")
    analysis_id = await _run(client, alice)

    assert (
        await client.get(f"/api/v1/analyses/{analysis_id}/readiness", headers=bob.headers)
    ).status_code == 404
    assert (
        await client.patch(
            f"/api/v1/analyses/{analysis_id}/readiness/override",
            json={"decision_label": "strong_bid", "reason": "attempted hijack"},
            headers=bob.headers,
        )
    ).status_code == 404


async def test_unknown_analysis_readiness_is_404(client: AsyncClient) -> None:
    actor = await sign_up(client)
    assert (
        await client.get(f"/api/v1/analyses/{uuid.uuid4()}/readiness", headers=actor.headers)
    ).status_code == 404
