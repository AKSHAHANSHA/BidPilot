"""Tender CRUD, secure upload, and ownership against real PostgreSQL and the filesystem.

Includes the roadmap's literal Phase 1 exit test, now that tenders exist:
"User A cannot access User B's tender."
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import AsyncClient

from tests.conftest import TEST_UPLOAD_DIR
from tests.integration.factories import make_pdf
from tests.integration.test_company_api import Signed, sign_up

pytestmark = pytest.mark.integration

PAGE_TEXT = (
    "The bidder shall maintain a valid ISO 9001 certificate for the duration of the contract "
    "and shall provide evidence of renewal not later than thirty days before expiry."
)
PDF = make_pdf(f"Page one. {PAGE_TEXT}", f"Page two. {PAGE_TEXT}")


def pdf_upload(
    content: bytes = PDF, filename: str = "tender.pdf"
) -> dict[str, tuple[str, bytes, str]]:
    return {"file": (filename, content, "application/pdf")}


async def create_tender(client: AsyncClient, actor: Signed, **overrides: object) -> str:
    payload: dict[str, object] = {
        "title": "Integrated FM Services - Government Campus",
        "buyer": "Fictional Government Entity (demo)",
        "reference": "RFP-DEMO-2026-014",
        "industry": "Facilities Management",
        "submission_deadline": (datetime.now(tz=UTC) + timedelta(days=30)).isoformat(),
    }
    payload.update(overrides)
    response = await client.post("/api/v1/tenders", json=payload, headers=actor.headers)
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


# --- Tender CRUD -------------------------------------------------------------------------


async def test_tender_crud_round_trip(client: AsyncClient) -> None:
    actor = await sign_up(client)
    tender_id = await create_tender(client, actor)

    fetched = await client.get(f"/api/v1/tenders/{tender_id}", headers=actor.headers)
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "active"
    assert fetched.json()["document_count"] == 0

    patched = await client.patch(
        f"/api/v1/tenders/{tender_id}",
        json={"status": "archived", "notes": "Deprioritized."},
        headers=actor.headers,
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "archived"

    assert (
        await client.delete(f"/api/v1/tenders/{tender_id}", headers=actor.headers)
    ).status_code == 204
    assert (
        await client.get(f"/api/v1/tenders/{tender_id}", headers=actor.headers)
    ).status_code == 404


async def test_tender_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/tenders")).status_code == 401
    assert (await client.post("/api/v1/tenders", json={})).status_code == 401


async def test_tender_filters_and_pagination(client: AsyncClient) -> None:
    actor = await sign_up(client)
    await create_tender(client, actor, title="Campus FM tender")
    archived_id = await create_tender(client, actor, title="Old cleaning tender")
    await client.patch(
        f"/api/v1/tenders/{archived_id}", json={"status": "archived"}, headers=actor.headers
    )

    async def query(params: str) -> dict[str, object]:
        response = await client.get(f"/api/v1/tenders?{params}", headers=actor.headers)
        assert response.status_code == 200, response.text
        return response.json()

    active = await query("status=active")
    assert [t["title"] for t in active["items"]] == ["Campus FM tender"]
    assert (await query("search=cleaning"))["total"] == 1
    paged = await query("limit=1")
    assert paged["total"] == 2
    assert len(paged["items"]) == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", ""),
        ("title", "   "),
        ("submission_deadline", "2026-09-01T12:00:00"),  # naive datetime
        ("notes", "x" * 4001),
    ],
)
async def test_invalid_tender_payloads_are_rejected(
    client: AsyncClient, field: str, value: object
) -> None:
    actor = await sign_up(client)
    payload = {"title": "Valid title", field: value}
    response = await client.post("/api/v1/tenders", json=payload, headers=actor.headers)
    assert response.status_code == 422, f"{field}={value!r} was accepted"


# --- Upload ------------------------------------------------------------------------------


async def test_valid_pdf_is_stored_on_disk_and_recorded(client: AsyncClient) -> None:
    actor = await sign_up(client)
    tender_id = await create_tender(client, actor)

    response = await client.post(
        f"/api/v1/tenders/{tender_id}/documents", files=pdf_upload(), headers=actor.headers
    )
    assert response.status_code == 201, response.text
    document = response.json()
    assert document["original_filename"] == "tender.pdf"
    assert document["size_bytes"] == len(PDF)
    # Extraction runs at upload time (docs/08 D37): pages exist immediately.
    assert document["extraction_status"] == "extracted"
    assert document["page_count"] == 2

    # The file genuinely exists under the server-generated key.
    stored = Path(TEST_UPLOAD_DIR) / str(actor.user_id) / tender_id
    files = list(stored.glob("*.pdf"))
    assert len(files) == 1
    assert files[0].read_bytes() == PDF

    # And the tender now reports one document.
    tender = await client.get(f"/api/v1/tenders/{tender_id}", headers=actor.headers)
    assert tender.json()["document_count"] == 1


async def test_non_pdf_bytes_are_rejected_with_problem_details(client: AsyncClient) -> None:
    actor = await sign_up(client)
    tender_id = await create_tender(client, actor)
    response = await client.post(
        f"/api/v1/tenders/{tender_id}/documents",
        files=pdf_upload(content=b"MZ\x90not a pdf", filename="malware.pdf"),
        headers=actor.headers,
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "UPLOAD_INVALID"
    assert body["request_id"]


async def test_rejected_upload_leaves_no_file_behind(client: AsyncClient) -> None:
    actor = await sign_up(client)
    tender_id = await create_tender(client, actor)
    await client.post(
        f"/api/v1/tenders/{tender_id}/documents",
        files=pdf_upload(content=b"not a pdf at all", filename="x.pdf"),
        headers=actor.headers,
    )
    tender_dir = Path(TEST_UPLOAD_DIR) / str(actor.user_id) / tender_id
    assert not tender_dir.exists() or list(tender_dir.iterdir()) == []


async def test_duplicate_upload_returns_conflict(client: AsyncClient) -> None:
    actor = await sign_up(client)
    tender_id = await create_tender(client, actor)
    first = await client.post(
        f"/api/v1/tenders/{tender_id}/documents", files=pdf_upload(), headers=actor.headers
    )
    assert first.status_code == 201

    duplicate = await client.post(
        f"/api/v1/tenders/{tender_id}/documents",
        files=pdf_upload(filename="renamed-copy.pdf"),  # same bytes, different name
        headers=actor.headers,
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "RESOURCE_CONFLICT"

    # Only the first file exists on disk.
    tender_dir = Path(TEST_UPLOAD_DIR) / str(actor.user_id) / tender_id
    assert len(list(tender_dir.glob("*.pdf"))) == 1


async def test_same_pdf_is_allowed_on_a_different_tender(client: AsyncClient) -> None:
    actor = await sign_up(client)
    first_tender = await create_tender(client, actor, title="Tender A")
    second_tender = await create_tender(client, actor, title="Tender B")
    for tender_id in (first_tender, second_tender):
        response = await client.post(
            f"/api/v1/tenders/{tender_id}/documents", files=pdf_upload(), headers=actor.headers
        )
        assert response.status_code == 201


async def test_path_traversal_filename_cannot_influence_storage(client: AsyncClient) -> None:
    actor = await sign_up(client)
    tender_id = await create_tender(client, actor)
    response = await client.post(
        f"/api/v1/tenders/{tender_id}/documents",
        files=pdf_upload(filename="../../../etc/evil.pdf"),
        headers=actor.headers,
    )
    assert response.status_code == 201
    # Display name is sanitized; the stored file sits under the generated key.
    assert response.json()["original_filename"] == "evil.pdf"
    upload_root = Path(TEST_UPLOAD_DIR).resolve()
    stored_files = list(upload_root.rglob("*.pdf"))
    assert all(f.resolve().is_relative_to(upload_root) for f in stored_files)


async def test_deleting_a_document_removes_the_file(client: AsyncClient) -> None:
    actor = await sign_up(client)
    tender_id = await create_tender(client, actor)
    created = await client.post(
        f"/api/v1/tenders/{tender_id}/documents", files=pdf_upload(), headers=actor.headers
    )
    document_id = created.json()["id"]
    tender_dir = Path(TEST_UPLOAD_DIR) / str(actor.user_id) / tender_id
    assert len(list(tender_dir.glob("*.pdf"))) == 1

    deleted = await client.delete(f"/api/v1/documents/{document_id}", headers=actor.headers)
    assert deleted.status_code == 204
    assert list(tender_dir.glob("*.pdf")) == []
    assert (
        await client.get(f"/api/v1/documents/{document_id}", headers=actor.headers)
    ).status_code == 404


async def test_deleting_a_tender_removes_rows_and_files(client: AsyncClient) -> None:
    actor = await sign_up(client)
    tender_id = await create_tender(client, actor)
    created = await client.post(
        f"/api/v1/tenders/{tender_id}/documents", files=pdf_upload(), headers=actor.headers
    )
    document_id = created.json()["id"]

    assert (
        await client.delete(f"/api/v1/tenders/{tender_id}", headers=actor.headers)
    ).status_code == 204

    assert (
        await client.get(f"/api/v1/documents/{document_id}", headers=actor.headers)
    ).status_code == 404
    tender_dir = Path(TEST_UPLOAD_DIR) / str(actor.user_id) / tender_id
    assert not tender_dir.exists() or list(tender_dir.glob("*.pdf")) == []


# --- Ownership: the roadmap's Phase 1 exit test, on real tenders ----------------------------


async def test_user_a_cannot_access_user_bs_tender(client: AsyncClient) -> None:
    alice = await sign_up(client, "alice")
    bob = await sign_up(client, "bob")
    tender_id = await create_tender(client, alice)

    assert (
        await client.get(f"/api/v1/tenders/{tender_id}", headers=bob.headers)
    ).status_code == 404
    assert (
        await client.patch(
            f"/api/v1/tenders/{tender_id}", json={"title": "hijack"}, headers=bob.headers
        )
    ).status_code == 404
    assert (
        await client.delete(f"/api/v1/tenders/{tender_id}", headers=bob.headers)
    ).status_code == 404
    # Bob cannot upload into Alice's tender either.
    assert (
        await client.post(
            f"/api/v1/tenders/{tender_id}/documents", files=pdf_upload(), headers=bob.headers
        )
    ).status_code == 404
    # Alice's tender is untouched.
    still = await client.get(f"/api/v1/tenders/{tender_id}", headers=alice.headers)
    assert still.status_code == 200
    assert still.json()["title"] != "hijack"


async def test_documents_are_isolated_between_users(client: AsyncClient) -> None:
    alice = await sign_up(client, "alice")
    bob = await sign_up(client, "bob")
    tender_id = await create_tender(client, alice)
    created = await client.post(
        f"/api/v1/tenders/{tender_id}/documents", files=pdf_upload(), headers=alice.headers
    )
    document_id = created.json()["id"]

    assert (
        await client.get(f"/api/v1/documents/{document_id}", headers=bob.headers)
    ).status_code == 404
    assert (
        await client.delete(f"/api/v1/documents/{document_id}", headers=bob.headers)
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/tenders/{tender_id}/documents", headers=bob.headers)
    ).status_code == 404


async def test_tender_lists_never_leak(client: AsyncClient) -> None:
    alice = await sign_up(client, "alice")
    bob = await sign_up(client, "bob")
    await create_tender(client, alice, title="Alice tender")

    bob_list = (await client.get("/api/v1/tenders", headers=bob.headers)).json()
    assert bob_list["total"] == 0
    assert bob_list["items"] == []
