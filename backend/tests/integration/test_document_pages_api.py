"""Phase 4 exit test: every page of an uploaded PDF is retrievable with correct numbering."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.integration.factories import make_pdf
from tests.integration.test_company_api import sign_up
from tests.integration.test_tender_api import create_tender, pdf_upload

pytestmark = pytest.mark.integration

PAGES = (
    "Section 1. The bidder shall hold a valid trade licence issued in the United Arab "
    "Emirates covering the licensed activities required for this contract scope.",
    "Section 2. The bidder shall maintain a valid ISO 9001 certificate — “quality first” — "
    "for the full duration of the contract period without interruption.",
    "Section 3. Liquidated damages of one percent per week of delay shall apply, capped at "
    "ten percent of the total contract value as stated in the particular conditions.",
)


async def upload(client: AsyncClient, actor: object) -> str:
    tender_id = await create_tender(client, actor)  # type: ignore[arg-type]
    response = await client.post(
        f"/api/v1/tenders/{tender_id}/documents",
        files=pdf_upload(content=make_pdf(*PAGES)),
        headers=actor.headers,  # type: ignore[attr-defined]
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def test_every_page_is_retrievable_with_correct_numbering(client: AsyncClient) -> None:
    actor = await sign_up(client)
    document_id = await upload(client, actor)

    summary = await client.get(f"/api/v1/documents/{document_id}/pages", headers=actor.headers)
    assert summary.status_code == 200
    pages = summary.json()
    assert [p["page_number"] for p in pages] == [1, 2, 3]
    assert all(p["extraction_method"] == "native" for p in pages)
    assert all(p["quality_score"] > 0 for p in pages)
    assert all("text" not in p for p in pages)  # summaries carry no text

    # Each page's text is retrievable and belongs to the right page.
    for number, expected in zip((1, 2, 3), ("Section 1", "Section 2", "Section 3"), strict=True):
        detail = await client.get(
            f"/api/v1/documents/{document_id}/pages/{number}", headers=actor.headers
        )
        assert detail.status_code == 200
        body = detail.json()
        assert body["page_number"] == number
        assert expected in body["text"]


async def test_normalization_is_applied_but_raw_text_is_served(client: AsyncClient) -> None:
    actor = await sign_up(client)
    document_id = await upload(client, actor)
    page_two = await client.get(f"/api/v1/documents/{document_id}/pages/2", headers=actor.headers)
    # The raw text keeps the PDF's curly quotes; normalization lives in normalized_text,
    # which is internal to citation matching and not part of the response.
    assert "quality first" in page_two.json()["text"]
    assert "normalized_text" not in page_two.json()


async def test_page_beyond_range_is_404(client: AsyncClient) -> None:
    actor = await sign_up(client)
    document_id = await upload(client, actor)
    response = await client.get(f"/api/v1/documents/{document_id}/pages/99", headers=actor.headers)
    assert response.status_code == 404


async def test_pages_are_ownership_isolated(client: AsyncClient) -> None:
    alice = await sign_up(client, "alice")
    bob = await sign_up(client, "bob")
    document_id = await upload(client, alice)

    assert (
        await client.get(f"/api/v1/documents/{document_id}/pages", headers=bob.headers)
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/documents/{document_id}/pages/1", headers=bob.headers)
    ).status_code == 404


async def test_textless_pdf_is_stored_as_unsupported_with_pages(client: AsyncClient) -> None:
    """A scanned/image-only document gets a clear status, not silent garbage."""
    actor = await sign_up(client)
    tender_id = await create_tender(client, actor)
    response = await client.post(
        f"/api/v1/tenders/{tender_id}/documents",
        files=pdf_upload(content=make_pdf("", "", "")),
        headers=actor.headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["extraction_status"] == "unsupported"
    assert body["page_count"] == 3

    # The pages exist so the UI can show why: every page is empty.
    pages = await client.get(f"/api/v1/documents/{body['id']}/pages", headers=actor.headers)
    assert [p["character_count"] for p in pages.json()] == [0, 0, 0]


async def test_corrupt_pdf_is_rejected_with_no_residue(client: AsyncClient) -> None:
    actor = await sign_up(client)
    tender_id = await create_tender(client, actor)
    response = await client.post(
        f"/api/v1/tenders/{tender_id}/documents",
        files=pdf_upload(content=b"%PDF-1.7 truncated garbage", filename="broken.pdf"),
        headers=actor.headers,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "DOCUMENT_UNREADABLE"
    # Nothing was stored.
    docs = await client.get(f"/api/v1/tenders/{tender_id}/documents", headers=actor.headers)
    assert docs.json() == []


async def test_deleting_a_document_removes_its_pages(client: AsyncClient) -> None:
    actor = await sign_up(client)
    document_id = await upload(client, actor)
    assert (
        await client.delete(f"/api/v1/documents/{document_id}", headers=actor.headers)
    ).status_code == 204
    assert (
        await client.get(f"/api/v1/documents/{document_id}/pages", headers=actor.headers)
    ).status_code == 404


async def test_page_number_zero_is_rejected(client: AsyncClient) -> None:
    actor = await sign_up(client)
    document_id = await upload(client, actor)
    response = await client.get(f"/api/v1/documents/{document_id}/pages/0", headers=actor.headers)
    assert response.status_code == 422


async def test_unknown_document_pages_are_404(client: AsyncClient) -> None:
    actor = await sign_up(client)
    response = await client.get(f"/api/v1/documents/{uuid.uuid4()}/pages", headers=actor.headers)
    assert response.status_code == 404
