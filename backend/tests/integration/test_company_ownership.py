"""Ownership isolation for the company knowledge base.

Proves the six properties Phase 2 requires: a user cannot read another's profile, cannot update
or delete another's evidence, cannot attach evidence to another's profile, gets 404 when guessing
a UUID, never sees another user's rows in a list, and cannot combine credentials with a foreign
resource ID to bypass the check.

The last one is enforced by the database rather than by a service check: evidence and projects
carry a composite foreign key on `(company_profile_id, owner_user_id)`, so a row referencing
another user's profile cannot exist.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company_evidence import CompanyEvidence
from tests.integration.factories import (
    make_profile,
    make_user,
    valid_evidence_payload,
    valid_project_payload,
)
from tests.integration.test_company_api import Signed, create_profile, sign_up

pytestmark = pytest.mark.integration


@pytest.fixture
async def two_users(client: AsyncClient) -> tuple[Signed, Signed]:
    """Alice and Bob, each with a profile, one evidence item, and one project."""
    alice = await sign_up(client, "alice")
    bob = await sign_up(client, "bob")
    await create_profile(client, alice, legal_name="Alice Facilities LLC")
    await create_profile(client, bob, legal_name="Bob Facilities LLC")
    return alice, bob


async def owned_ids(client: AsyncClient, actor: Signed) -> tuple[str, str]:
    evidence = await client.post(
        "/api/v1/company/evidence", json=valid_evidence_payload(), headers=actor.headers
    )
    project = await client.post(
        "/api/v1/company/projects", json=valid_project_payload(), headers=actor.headers
    )
    return evidence.json()["id"], project.json()["id"]


# --- 1. Profiles are not readable across users -----------------------------------------------


async def test_each_user_reads_only_their_own_profile(
    client: AsyncClient, two_users: tuple[Signed, Signed]
) -> None:
    alice, bob = two_users
    alice_view = await client.get("/api/v1/company", headers=alice.headers)
    bob_view = await client.get("/api/v1/company", headers=bob.headers)
    assert alice_view.json()["legal_name"] == "Alice Facilities LLC"
    assert bob_view.json()["legal_name"] == "Bob Facilities LLC"
    assert alice_view.json()["id"] != bob_view.json()["id"]


async def test_patching_the_profile_never_touches_another_users_record(
    client: AsyncClient, two_users: tuple[Signed, Signed]
) -> None:
    """There is no route that takes a profile ID, so a PATCH can only reach the caller's own."""
    alice, bob = two_users
    await client.patch(
        "/api/v1/company", json={"legal_name": "Alice Renamed LLC"}, headers=alice.headers
    )
    assert (await client.get("/api/v1/company", headers=bob.headers)).json()[
        "legal_name"
    ] == "Bob Facilities LLC"


# --- 2 & 3. Evidence and projects cannot be read, updated, or deleted across users -------------


@pytest.mark.parametrize("resource", ["evidence", "projects"])
async def test_another_user_cannot_read_update_or_delete(
    client: AsyncClient, two_users: tuple[Signed, Signed], resource: str
) -> None:
    alice, bob = two_users
    evidence_id, project_id = await owned_ids(client, alice)
    target = evidence_id if resource == "evidence" else project_id
    path = f"/api/v1/company/{resource}/{target}"

    assert (await client.get(path, headers=bob.headers)).status_code == 404
    assert (
        await client.patch(path, json={"description": "hijacked"}, headers=bob.headers)
    ).status_code == 404
    assert (await client.delete(path, headers=bob.headers)).status_code == 404

    # Alice's record is untouched.
    still_there = await client.get(path, headers=alice.headers)
    assert still_there.status_code == 200
    assert still_there.json()["description"] != "hijacked"


# --- 4. Guessing a UUID returns 404 ------------------------------------------------------------


@pytest.mark.parametrize("resource", ["evidence", "projects"])
async def test_guessing_a_random_uuid_is_404_not_403(
    client: AsyncClient, two_users: tuple[Signed, Signed], resource: str
) -> None:
    """404 for both "absent" and "someone else's" — a 403 would confirm the row exists."""
    alice, _ = two_users
    response = await client.get(f"/api/v1/company/{resource}/{uuid.uuid4()}", headers=alice.headers)
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"


async def test_absent_and_foreign_resources_are_indistinguishable(
    client: AsyncClient, two_users: tuple[Signed, Signed]
) -> None:
    alice, bob = two_users
    evidence_id, _ = await owned_ids(client, alice)

    foreign = await client.get(f"/api/v1/company/evidence/{evidence_id}", headers=bob.headers)
    absent = await client.get(f"/api/v1/company/evidence/{uuid.uuid4()}", headers=bob.headers)

    assert foreign.status_code == absent.status_code == 404
    assert foreign.json()["code"] == absent.json()["code"]
    assert foreign.json()["detail"] == absent.json()["detail"]


# --- 5. Lists never leak ------------------------------------------------------------------------


async def test_evidence_list_is_scoped_to_the_caller(
    client: AsyncClient, two_users: tuple[Signed, Signed]
) -> None:
    alice, bob = two_users
    for index in range(3):
        await client.post(
            "/api/v1/company/evidence",
            json=valid_evidence_payload(title=f"Alice item {index}"),
            headers=alice.headers,
        )
    await client.post(
        "/api/v1/company/evidence",
        json=valid_evidence_payload(title="Bob item"),
        headers=bob.headers,
    )

    alice_list = (await client.get("/api/v1/company/evidence", headers=alice.headers)).json()
    bob_list = (await client.get("/api/v1/company/evidence", headers=bob.headers)).json()

    assert alice_list["total"] == 3
    assert bob_list["total"] == 1
    assert all("Alice" in item["title"] for item in alice_list["items"])
    assert all("Bob" in item["title"] for item in bob_list["items"])


async def test_project_list_is_scoped_to_the_caller(
    client: AsyncClient, two_users: tuple[Signed, Signed]
) -> None:
    alice, bob = two_users
    await client.post(
        "/api/v1/company/projects",
        json=valid_project_payload(project_title="Alice project"),
        headers=alice.headers,
    )
    alice_list = (await client.get("/api/v1/company/projects", headers=alice.headers)).json()
    bob_list = (await client.get("/api/v1/company/projects", headers=bob.headers)).json()
    assert alice_list["total"] == 1
    assert bob_list["total"] == 0


async def test_filters_cannot_widen_scope_beyond_the_owner(
    client: AsyncClient, two_users: tuple[Signed, Signed]
) -> None:
    """A filter narrows a scoped set; it must never be a way to reach other rows."""
    alice, bob = two_users
    await client.post(
        "/api/v1/company/evidence",
        json=valid_evidence_payload(title="Alice licence", category="trade_licence"),
        headers=alice.headers,
    )
    for params in (
        "category=trade_licence",
        "verification_status=verified",
        "expiry_state=active",
        "search=Alice",
        "tag=iso",
        "limit=100&offset=0",
    ):
        response = await client.get(f"/api/v1/company/evidence?{params}", headers=bob.headers)
        assert response.status_code == 200
        assert response.json()["items"] == [], params


# --- 6. Mixed credentials and foreign resource IDs cannot bypass ownership ---------------------


async def test_evidence_is_attached_to_the_callers_own_profile_only(
    client: AsyncClient, two_users: tuple[Signed, Signed]
) -> None:
    """The profile ID is never read from the request body.

    Even a body that names Bob's profile produces evidence on Alice's, because the service takes
    the ID from the authenticated user's own profile.
    """
    alice, bob = two_users
    alice_profile = (await client.get("/api/v1/company", headers=alice.headers)).json()
    bob_profile = (await client.get("/api/v1/company", headers=bob.headers)).json()

    created = await client.post(
        "/api/v1/company/evidence",
        json={
            **valid_evidence_payload(),
            "company_profile_id": bob_profile["id"],
            "owner_user_id": str(bob.user_id),
        },
        headers=alice.headers,
    )
    assert created.status_code == 201
    assert created.json()["company_profile_id"] == alice_profile["id"]

    # Bob's list is still empty, so nothing landed on his profile.
    assert (await client.get("/api/v1/company/evidence", headers=bob.headers)).json()["total"] == 0


async def test_database_rejects_evidence_pointing_at_another_users_profile(
    db_session: AsyncSession,
) -> None:
    """The composite foreign key makes the cross-user row unrepresentable.

    This bypasses the API entirely — a future route, script, or migration that got the owner
    wrong would still be stopped here.
    """
    alice = await make_user(db_session, "alice")
    bob = await make_user(db_session, "bob")
    bob_profile = await make_profile(db_session, bob.id)

    db_session.add(
        CompanyEvidence(
            owner_user_id=alice.id,  # Alice…
            company_profile_id=bob_profile.id,  # …pointing at Bob's profile
            title="Smuggled evidence",
            category="certification",
            description="Should never be insertable.",
            verification_status="verified",
            tags=[],
        )
    )
    with pytest.raises(IntegrityError) as exc_info:
        await db_session.flush()
    assert "fk_company_evidence_profile_owner" in str(exc_info.value)


async def test_a_second_profile_is_rejected_by_the_database(db_session: AsyncSession) -> None:
    """The one-profile rule is a unique constraint, not just a service check."""
    user = await make_user(db_session)
    await make_profile(db_session, user.id)
    # `make_profile` flushes, so the violation surfaces from the helper itself.
    with pytest.raises(IntegrityError) as exc_info:
        await make_profile(db_session, user.id, legal_name="Second Profile LLC")
    assert "uq_company_profiles_owner_user_id" in str(exc_info.value)


async def test_deleting_a_user_cascades_to_the_whole_knowledge_base(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    from sqlalchemy import func, select

    from app.models.company_profile import CompanyProfile
    from app.models.user import User
    from app.repositories.user_repository import UserRepository

    actor = await sign_up(client, "departing")
    await create_profile(client, actor)
    await client.post(
        "/api/v1/company/evidence", json=valid_evidence_payload(), headers=actor.headers
    )

    users = UserRepository(db_session)
    user = await users.get_by_id(actor.user_id)
    assert user is not None
    await db_session.delete(user)
    await db_session.flush()

    for model in (CompanyProfile, CompanyEvidence, User):
        remaining = await db_session.execute(
            select(func.count())
            .select_from(model)
            .where(getattr(model, "owner_user_id", model.id) == actor.user_id)
        )
        assert remaining.scalar_one() == 0, model.__name__
