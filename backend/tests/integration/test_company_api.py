"""Company profile, evidence, and project CRUD against real PostgreSQL."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
from httpx import AsyncClient

from app.core.config import Settings
from app.core.constants import PROBLEM_JSON_MEDIA_TYPE
from tests.integration.factories import (
    iso,
    valid_evidence_payload,
    valid_profile_payload,
    valid_project_payload,
)

pytestmark = pytest.mark.integration

PASSWORD = "a-long-demo-passphrase-1"


@dataclass
class Signed:
    user_id: uuid.UUID
    headers: dict[str, str]


async def sign_up(client: AsyncClient, label: str = "user") -> Signed:
    email = f"{label}-{uuid.uuid4().hex[:12]}@fm-demo.ae"
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "display_name": "Coordinator"},
    )
    assert response.status_code == 201, response.text
    client.cookies.clear()
    body = response.json()
    return Signed(
        user_id=uuid.UUID(body["user"]["id"]),
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )


async def create_profile(
    client: AsyncClient, actor: Signed, **overrides: object
) -> dict[str, object]:
    response = await client.post(
        "/api/v1/company", json=valid_profile_payload(**overrides), headers=actor.headers
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- Profile: creation and the one-profile rule ---------------------------------------------


async def test_create_profile_returns_the_stored_record(client: AsyncClient) -> None:
    actor = await sign_up(client)
    body = await create_profile(client, actor)
    assert body["legal_name"] == "Al Mirqab Integrated Facilities Management LLC"
    assert body["emirate"] == "dubai"
    assert body["service_categories"] == ["Hard FM", "Soft FM", "HVAC maintenance"]
    assert body["profile_completion_percentage"] == 100


async def test_profile_requires_authentication(client: AsyncClient) -> None:
    assert (await client.post("/api/v1/company", json={})).status_code == 401
    assert (await client.get("/api/v1/company")).status_code == 401
    assert (await client.patch("/api/v1/company", json={})).status_code == 401
    assert (await client.delete("/api/v1/company")).status_code == 401


async def test_evidence_and_project_routes_require_authentication(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/company/evidence")).status_code == 401
    assert (await client.post("/api/v1/company/evidence", json={})).status_code == 401
    assert (await client.get("/api/v1/company/projects")).status_code == 401
    assert (await client.post("/api/v1/company/projects", json={})).status_code == 401


async def test_get_profile_before_creation_is_404(client: AsyncClient) -> None:
    actor = await sign_up(client)
    response = await client.get("/api/v1/company", headers=actor.headers)
    assert response.status_code == 404
    assert response.headers["content-type"].startswith(PROBLEM_JSON_MEDIA_TYPE)
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"


async def test_second_profile_is_rejected_with_conflict(client: AsyncClient) -> None:
    """One profile per user, enforced by a unique constraint on owner_user_id."""
    actor = await sign_up(client)
    await create_profile(client, actor)
    response = await client.post(
        "/api/v1/company", json=valid_profile_payload(), headers=actor.headers
    )
    assert response.status_code == 409
    assert response.json()["code"] == "RESOURCE_CONFLICT"


async def test_two_users_each_get_their_own_profile(client: AsyncClient) -> None:
    alice = await sign_up(client, "alice")
    bob = await sign_up(client, "bob")
    alice_profile = await create_profile(client, alice, legal_name="Alice FM LLC")
    bob_profile = await create_profile(client, bob, legal_name="Bob FM LLC")
    assert alice_profile["id"] != bob_profile["id"]


# --- Profile: update and completion recalculation --------------------------------------------


async def test_patch_updates_only_supplied_fields(client: AsyncClient) -> None:
    actor = await sign_up(client)
    original = await create_profile(client, actor)

    response = await client.patch(
        "/api/v1/company", json={"employee_count": 120}, headers=actor.headers
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["employee_count"] == 120
    assert updated["legal_name"] == original["legal_name"]
    assert updated["service_categories"] == original["service_categories"]


async def test_completion_recalculates_downward_when_detail_is_removed(
    client: AsyncClient,
) -> None:
    actor = await sign_up(client)
    complete = await create_profile(client, actor)
    assert complete["profile_completion_percentage"] == 100

    response = await client.patch(
        "/api/v1/company",
        json={"website": None, "contact_phone": None, "trading_name": None},
        headers=actor.headers,
    )
    assert response.status_code == 200
    assert response.json()["profile_completion_percentage"] < 100


async def test_completion_recalculates_upward_and_reports_missing_items(
    client: AsyncClient,
) -> None:
    actor = await sign_up(client)
    sparse = await create_profile(
        client,
        actor,
        trading_name=None,
        website=None,
        contact_phone=None,
        annual_revenue_range=None,
        preferred_contract_value_min=None,
        preferred_contract_value_max=None,
        licence_activities=["Building cleaning services"],
        service_categories=["Hard FM"],
        geographic_coverage=["Dubai"],
    )
    assert sparse["profile_completion_percentage"] < 100
    missing_keys = {item["key"] for item in sparse["completion"]["missing"]}
    assert "website" in missing_keys
    assert "service_categories_detail" in missing_keys

    response = await client.patch(
        "/api/v1/company",
        json={"website": "https://almirqab-fm.example.ae"},
        headers=actor.headers,
    )
    assert (
        response.json()["profile_completion_percentage"] > sparse["profile_completion_percentage"]
    )


async def test_completion_breakdown_is_returned_with_weights(client: AsyncClient) -> None:
    actor = await sign_up(client)
    body = await create_profile(client, actor)
    completion = body["completion"]
    assert completion["version"] == "1.0.0"
    assert sum(component["weight"] for component in completion["components"]) == 100
    assert all("hint" in component for component in completion["components"])


async def test_patch_rejects_unknown_fields(client: AsyncClient) -> None:
    actor = await sign_up(client)
    await create_profile(client, actor)
    response = await client.patch(
        "/api/v1/company", json={"nonexistent_field": "x"}, headers=actor.headers
    )
    assert response.status_code == 422


# --- Profile: validation ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("year_established", 2999),
        ("employee_count", -1),
        ("years_of_experience", -5),
        ("contact_email", "not-an-email"),
        ("website", "not-a-url"),
        ("emirate", "atlantis"),
        ("service_categories", []),
        ("geographic_coverage", []),
        ("annual_revenue_range", "a_lot_of_money"),
    ],
)
async def test_invalid_profile_values_are_rejected(
    client: AsyncClient, field: str, value: object
) -> None:
    actor = await sign_up(client)
    response = await client.post(
        "/api/v1/company", json=valid_profile_payload(**{field: value}), headers=actor.headers
    )
    assert response.status_code == 422, f"{field}={value!r} was accepted"
    assert response.json()["code"] == "REQUEST_VALIDATION_FAILED"


async def test_a_thin_description_is_accepted_but_earns_no_completion_credit(
    client: AsyncClient,
) -> None:
    """Validation and completion answer different questions.

    "FM company" is a legal value to store, so it is not a 422; it is simply not a description
    worth scoring, so the completion rule withholds its weight and lists it as missing.
    """
    actor = await sign_up(client)
    body = await create_profile(client, actor, description="FM company")
    assert body["profile_completion_percentage"] < 100
    assert "description" in {item["key"] for item in body["completion"]["missing"]}


async def test_overlong_description_is_rejected(client: AsyncClient) -> None:
    actor = await sign_up(client)
    response = await client.post(
        "/api/v1/company",
        json=valid_profile_payload(description="x" * 4001),
        headers=actor.headers,
    )
    assert response.status_code == 422


async def test_contract_minimum_above_maximum_is_rejected(client: AsyncClient) -> None:
    actor = await sign_up(client)
    response = await client.post(
        "/api/v1/company",
        json=valid_profile_payload(
            preferred_contract_value_min="9000000.00",
            preferred_contract_value_max="1000000.00",
        ),
        headers=actor.headers,
    )
    assert response.status_code == 422


async def test_one_sided_patch_is_validated_against_stored_value(client: AsyncClient) -> None:
    """A PATCH supplying only the minimum must still be checked against the stored maximum."""
    actor = await sign_up(client)
    await create_profile(
        client,
        actor,
        preferred_contract_value_min="500000.00",
        preferred_contract_value_max="1000000.00",
    )
    response = await client.patch(
        "/api/v1/company",
        json={"preferred_contract_value_min": "9000000.00"},
        headers=actor.headers,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_INVALID"


async def test_experience_cannot_exceed_company_age(client: AsyncClient) -> None:
    actor = await sign_up(client)
    response = await client.post(
        "/api/v1/company",
        json=valid_profile_payload(year_established=2020, years_of_experience=40),
        headers=actor.headers,
    )
    assert response.status_code == 422


async def test_duplicate_array_entries_are_collapsed(client: AsyncClient) -> None:
    actor = await sign_up(client)
    body = await create_profile(
        client, actor, service_categories=["Hard FM", "hard fm", " Hard FM ", "Soft FM"]
    )
    assert body["service_categories"] == ["Hard FM", "Soft FM"]


# --- Evidence ---------------------------------------------------------------------------------


async def test_evidence_requires_a_profile_first(client: AsyncClient) -> None:
    actor = await sign_up(client)
    response = await client.post(
        "/api/v1/company/evidence", json=valid_evidence_payload(), headers=actor.headers
    )
    assert response.status_code == 422
    assert "profile" in response.json()["detail"].lower()


async def test_evidence_crud_round_trip(client: AsyncClient) -> None:
    actor = await sign_up(client)
    profile = await create_profile(client, actor)

    created = await client.post(
        "/api/v1/company/evidence", json=valid_evidence_payload(), headers=actor.headers
    )
    assert created.status_code == 201, created.text
    evidence = created.json()
    assert evidence["company_profile_id"] == profile["id"]
    assert evidence["tags"] == ["iso", "quality"]
    assert evidence["attachment"] is None

    fetched = await client.get(f"/api/v1/company/evidence/{evidence['id']}", headers=actor.headers)
    assert fetched.status_code == 200
    assert fetched.json()["title"] == evidence["title"]

    patched = await client.patch(
        f"/api/v1/company/evidence/{evidence['id']}",
        json={"title": "ISO 9001:2015 (renewed)", "verification_status": "unverified"},
        headers=actor.headers,
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "ISO 9001:2015 (renewed)"
    assert patched.json()["expiry"]["state"] == "unverified"

    deleted = await client.delete(
        f"/api/v1/company/evidence/{evidence['id']}", headers=actor.headers
    )
    assert deleted.status_code == 204

    gone = await client.get(f"/api/v1/company/evidence/{evidence['id']}", headers=actor.headers)
    assert gone.status_code == 404


async def test_evidence_tags_are_normalized(client: AsyncClient) -> None:
    actor = await sign_up(client)
    await create_profile(client, actor)
    created = await client.post(
        "/api/v1/company/evidence",
        json=valid_evidence_payload(tags=["ISO", "iso", " Quality ", "quality"]),
        headers=actor.headers,
    )
    assert created.json()["tags"] == ["iso", "quality"]


async def test_expiry_before_issue_date_is_rejected(client: AsyncClient) -> None:
    actor = await sign_up(client)
    await create_profile(client, actor)
    response = await client.post(
        "/api/v1/company/evidence",
        json=valid_evidence_payload(issue_date=iso(-10), expiry_date=iso(-100)),
        headers=actor.headers,
    )
    assert response.status_code == 422


async def test_patch_cannot_invert_the_evidence_dates(client: AsyncClient) -> None:
    """Checked against the persisted issue date, since only the expiry is supplied."""
    actor = await sign_up(client)
    await create_profile(client, actor)
    created = await client.post(
        "/api/v1/company/evidence",
        json=valid_evidence_payload(issue_date=iso(-30), expiry_date=iso(300)),
        headers=actor.headers,
    )
    evidence_id = created.json()["id"]

    response = await client.patch(
        f"/api/v1/company/evidence/{evidence_id}",
        json={"expiry_date": iso(-100)},
        headers=actor.headers,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "REQUEST_INVALID"


async def test_unknown_evidence_id_is_404(client: AsyncClient) -> None:
    actor = await sign_up(client)
    await create_profile(client, actor)
    response = await client.get(f"/api/v1/company/evidence/{uuid.uuid4()}", headers=actor.headers)
    assert response.status_code == 404


# --- Evidence: derived expiry over HTTP -------------------------------------------------------


@pytest.mark.parametrize(
    ("offset", "status", "expected"),
    [
        (400, "verified", "active"),
        (30, "verified", "expiring_soon"),
        (-30, "verified", "expired"),
        (None, "verified", "no_expiry"),
        (400, "unverified", "unverified"),
        (-30, "unverified", "expired"),
    ],
)
async def test_expiry_state_is_derived_in_responses(
    client: AsyncClient,
    settings: Settings,
    offset: int | None,
    status: str,
    expected: str,
) -> None:
    actor = await sign_up(client)
    await create_profile(client, actor)
    created = await client.post(
        "/api/v1/company/evidence",
        json=valid_evidence_payload(
            issue_date=None,
            expiry_date=None if offset is None else iso(offset),
            verification_status=status,
        ),
        headers=actor.headers,
    )
    assert created.status_code == 201, created.text
    expiry = created.json()["expiry"]
    assert expiry["state"] == expected
    assert expiry["threshold_days"] == settings.evidence_expiring_soon_days
    if offset is None:
        assert expiry["days_until_expiry"] is None
    else:
        assert expiry["days_until_expiry"] == offset


# --- Evidence: filters and pagination ---------------------------------------------------------


async def test_evidence_filters(client: AsyncClient) -> None:
    actor = await sign_up(client)
    await create_profile(client, actor)

    await client.post(
        "/api/v1/company/evidence",
        json=valid_evidence_payload(
            title="Trade licence", category="trade_licence", tags=["licence"]
        ),
        headers=actor.headers,
    )
    await client.post(
        "/api/v1/company/evidence",
        json=valid_evidence_payload(
            title="ISO 14001 pending",
            category="certification",
            verification_status="unverified",
            expiry_date=None,
            issue_date=None,
            tags=["iso", "gap"],
        ),
        headers=actor.headers,
    )
    await client.post(
        "/api/v1/company/evidence",
        json=valid_evidence_payload(
            title="Liability insurance", category="insurance", expiry_date=iso(20), tags=[]
        ),
        headers=actor.headers,
    )

    async def query(params: str) -> list[dict[str, object]]:
        response = await client.get(f"/api/v1/company/evidence?{params}", headers=actor.headers)
        assert response.status_code == 200, response.text
        return response.json()["items"]

    assert {item["title"] for item in await query("category=insurance")} == {"Liability insurance"}
    assert {item["title"] for item in await query("verification_status=unverified")} == {
        "ISO 14001 pending"
    }
    assert {item["title"] for item in await query("expiry_state=expiring_soon")} == {
        "Liability insurance"
    }
    assert {item["title"] for item in await query("tag=iso")} == {"ISO 14001 pending"}
    assert {item["title"] for item in await query("search=insurance")} == {"Liability insurance"}
    # Filters combine with AND.
    assert await query("category=insurance&verification_status=unverified") == []


async def test_search_matches_description_and_escapes_wildcards(client: AsyncClient) -> None:
    actor = await sign_up(client)
    await create_profile(client, actor)
    await client.post(
        "/api/v1/company/evidence",
        json=valid_evidence_payload(title="Cover note", description="Covers 100% of the fleet."),
        headers=actor.headers,
    )

    hit = await client.get("/api/v1/company/evidence?search=100%25", headers=actor.headers)
    assert len(hit.json()["items"]) == 1

    # A literal "%" must not behave as a wildcard.
    miss = await client.get("/api/v1/company/evidence?search=%25zzz", headers=actor.headers)
    assert miss.json()["items"] == []


async def test_evidence_pagination_reports_total_and_slices(client: AsyncClient) -> None:
    actor = await sign_up(client)
    await create_profile(client, actor)
    for index in range(5):
        await client.post(
            "/api/v1/company/evidence",
            json=valid_evidence_payload(title=f"Item {index}"),
            headers=actor.headers,
        )

    first = await client.get("/api/v1/company/evidence?limit=2&offset=0", headers=actor.headers)
    body = first.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["limit"] == 2 and body["offset"] == 0

    last = await client.get("/api/v1/company/evidence?limit=2&offset=4", headers=actor.headers)
    assert len(last.json()["items"]) == 1

    beyond = await client.get("/api/v1/company/evidence?limit=2&offset=99", headers=actor.headers)
    assert beyond.json()["items"] == []
    assert beyond.json()["total"] == 5


async def test_pagination_limit_is_bounded(client: AsyncClient) -> None:
    actor = await sign_up(client)
    await create_profile(client, actor)
    assert (
        await client.get("/api/v1/company/evidence?limit=1000", headers=actor.headers)
    ).status_code == 422
    assert (
        await client.get("/api/v1/company/evidence?offset=-1", headers=actor.headers)
    ).status_code == 422


# --- Projects ---------------------------------------------------------------------------------


async def test_project_crud_round_trip(client: AsyncClient) -> None:
    actor = await sign_up(client)
    profile = await create_profile(client, actor)

    created = await client.post(
        "/api/v1/company/projects",
        # Fixed dates rather than offsets: duration is asserted exactly, and day-of-month drift
        # in an offset-derived range would make the expected value depend on the run date.
        json=valid_project_payload(start_date="2021-01-01", end_date="2024-01-01"),
        headers=actor.headers,
    )
    assert created.status_code == 201, created.text
    project = created.json()
    assert project["company_profile_id"] == profile["id"]
    assert project["currency"] == "AED"
    assert project["duration_months"] == 36

    fetched = await client.get(f"/api/v1/company/projects/{project['id']}", headers=actor.headers)
    assert fetched.status_code == 200

    patched = await client.patch(
        f"/api/v1/company/projects/{project['id']}",
        json={"outcome": "Renewed twice."},
        headers=actor.headers,
    )
    assert patched.json()["outcome"] == "Renewed twice."

    assert (
        await client.delete(f"/api/v1/company/projects/{project['id']}", headers=actor.headers)
    ).status_code == 204
    assert (
        await client.get(f"/api/v1/company/projects/{project['id']}", headers=actor.headers)
    ).status_code == 404


async def test_current_project_has_no_end_date_and_no_duration(client: AsyncClient) -> None:
    actor = await sign_up(client)
    await create_profile(client, actor)
    created = await client.post(
        "/api/v1/company/projects",
        json=valid_project_payload(status="current", end_date=None),
        headers=actor.headers,
    )
    assert created.status_code == 201
    assert created.json()["duration_months"] is None


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"status": "current", "end_date": iso(-10)}, "current project with an end date"),
        ({"status": "completed", "end_date": None}, "completed project without an end date"),
        ({"start_date": iso(-10), "end_date": iso(-100)}, "end before start"),
        ({"contract_value": "-5000.00"}, "negative contract value"),
        ({"services_delivered": []}, "no services"),
        ({"start_date": iso(30)}, "start date in the future"),
        ({"currency": "dirhams"}, "invalid currency code"),
    ],
)
async def test_invalid_project_payloads_are_rejected(
    client: AsyncClient, overrides: dict[str, object], reason: str
) -> None:
    actor = await sign_up(client)
    await create_profile(client, actor)
    response = await client.post(
        "/api/v1/company/projects",
        json=valid_project_payload(**overrides),
        headers=actor.headers,
    )
    assert response.status_code == 422, f"accepted {reason}"


async def test_patch_to_completed_requires_an_end_date(client: AsyncClient) -> None:
    """The combined state is judged against persisted values, not just the payload."""
    actor = await sign_up(client)
    await create_profile(client, actor)
    created = await client.post(
        "/api/v1/company/projects",
        json=valid_project_payload(status="current", end_date=None),
        headers=actor.headers,
    )
    project_id = created.json()["id"]

    invalid = await client.patch(
        f"/api/v1/company/projects/{project_id}",
        json={"status": "completed"},
        headers=actor.headers,
    )
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "REQUEST_INVALID"

    valid = await client.patch(
        f"/api/v1/company/projects/{project_id}",
        json={"status": "completed", "end_date": iso(-1)},
        headers=actor.headers,
    )
    assert valid.status_code == 200


async def test_patch_adding_an_end_date_to_a_current_project_is_rejected(
    client: AsyncClient,
) -> None:
    actor = await sign_up(client)
    await create_profile(client, actor)
    created = await client.post(
        "/api/v1/company/projects",
        json=valid_project_payload(status="current", end_date=None),
        headers=actor.headers,
    )
    response = await client.patch(
        f"/api/v1/company/projects/{created.json()['id']}",
        json={"end_date": iso(-1)},
        headers=actor.headers,
    )
    assert response.status_code == 422


async def test_project_filters_and_pagination(client: AsyncClient) -> None:
    actor = await sign_up(client)
    await create_profile(client, actor)
    await client.post(
        "/api/v1/company/projects",
        json=valid_project_payload(project_title="Retail centre", services_delivered=["Soft FM"]),
        headers=actor.headers,
    )
    await client.post(
        "/api/v1/company/projects",
        json=valid_project_payload(
            project_title="Tower MEP",
            status="current",
            end_date=None,
            services_delivered=["Hard FM"],
        ),
        headers=actor.headers,
    )

    async def query(params: str) -> list[dict[str, object]]:
        response = await client.get(f"/api/v1/company/projects?{params}", headers=actor.headers)
        assert response.status_code == 200, response.text
        return response.json()["items"]

    assert {p["project_title"] for p in await query("status=current")} == {"Tower MEP"}
    assert {p["project_title"] for p in await query("service=Soft FM")} == {"Retail centre"}
    assert {p["project_title"] for p in await query("search=tower")} == {"Tower MEP"}
    assert len(await query("limit=1")) == 1


async def test_confidential_flag_round_trips(client: AsyncClient) -> None:
    actor = await sign_up(client)
    await create_profile(client, actor)
    created = await client.post(
        "/api/v1/company/projects",
        json=valid_project_payload(is_confidential=True, client_reference_available=False),
        headers=actor.headers,
    )
    assert created.json()["is_confidential"] is True


# --- Deletion and cascade ---------------------------------------------------------------------


async def test_deleting_the_profile_cascades_to_evidence_and_projects(
    client: AsyncClient,
) -> None:
    actor = await sign_up(client)
    await create_profile(client, actor)
    evidence = await client.post(
        "/api/v1/company/evidence", json=valid_evidence_payload(), headers=actor.headers
    )
    project = await client.post(
        "/api/v1/company/projects", json=valid_project_payload(), headers=actor.headers
    )

    deleted = await client.delete("/api/v1/company", headers=actor.headers)
    assert deleted.status_code == 204

    assert (await client.get("/api/v1/company", headers=actor.headers)).status_code == 404
    assert (
        await client.get(f"/api/v1/company/evidence/{evidence.json()['id']}", headers=actor.headers)
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/company/projects/{project.json()['id']}", headers=actor.headers)
    ).status_code == 404
    assert (await client.get("/api/v1/company/evidence", headers=actor.headers)).json()[
        "total"
    ] == 0


async def test_profile_can_be_recreated_after_deletion(client: AsyncClient) -> None:
    actor = await sign_up(client)
    await create_profile(client, actor)
    await client.delete("/api/v1/company", headers=actor.headers)
    recreated = await client.post(
        "/api/v1/company", json=valid_profile_payload(), headers=actor.headers
    )
    assert recreated.status_code == 201
