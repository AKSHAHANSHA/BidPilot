"""Ownership enforcement against a real database.

`tests/unit/test_ownership.py` proves the repository API cannot express an unowned lookup.
These tests prove the resulting SQL actually isolates users, and that a foreign key cascade
does not leave usable credentials behind.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_refresh_token, hash_password, hash_refresh_token
from app.models.refresh_session import RefreshSession
from app.repositories.refresh_session_repository import RefreshSessionRepository
from app.repositories.user_repository import UserRepository

pytestmark = pytest.mark.integration


async def make_user(session: AsyncSession, label: str) -> uuid.UUID:
    users = UserRepository(session)
    user = users.create(
        email=f"{label}-{uuid.uuid4().hex[:10]}@fm-demo.ae",
        password_hash=hash_password("a-long-demo-passphrase-1"),
        display_name=label,
    )
    await users.flush()
    return user.id


async def make_session(
    session: AsyncSession, user_id: uuid.UUID, *, expires_in: timedelta = timedelta(days=7)
) -> RefreshSession:
    sessions = RefreshSessionRepository(session)
    row = sessions.create(
        user_id=user_id,
        token_hash=hash_refresh_token(generate_refresh_token()),
        expires_at=datetime.now(tz=UTC) + expires_in,
        user_agent="pytest",
        ip_hash=None,
    )
    await sessions.flush()
    return row


async def test_owner_can_read_their_own_row(db_session: AsyncSession) -> None:
    user_id = await make_user(db_session, "owner")
    row = await make_session(db_session, user_id)

    found = await RefreshSessionRepository(db_session).get_for_user(row.id, user_id)
    assert found is not None
    assert found.id == row.id


async def test_another_user_gets_none_for_the_same_id(db_session: AsyncSession) -> None:
    """None, not an exception — the API turns this into 404, which does not confirm the row
    exists for somebody else."""
    owner_id = await make_user(db_session, "owner")
    intruder_id = await make_user(db_session, "intruder")
    row = await make_session(db_session, owner_id)

    found = await RefreshSessionRepository(db_session).get_for_user(row.id, intruder_id)
    assert found is None


async def test_listing_is_scoped_to_the_owner(db_session: AsyncSession) -> None:
    owner_id = await make_user(db_session, "owner")
    other_id = await make_user(db_session, "other")
    for _ in range(3):
        await make_session(db_session, owner_id)
    await make_session(db_session, other_id)

    repository = RefreshSessionRepository(db_session)
    assert len(await repository.list_for_user(owner_id)) == 3
    assert len(await repository.list_for_user(other_id)) == 1
    assert await repository.count_for_user(owner_id) == 3


async def test_delete_for_another_user_is_a_no_op(db_session: AsyncSession) -> None:
    owner_id = await make_user(db_session, "owner")
    intruder_id = await make_user(db_session, "intruder")
    row = await make_session(db_session, owner_id)

    repository = RefreshSessionRepository(db_session)
    assert await repository.delete_for_user(row.id, intruder_id) is False
    assert await repository.get_for_user(row.id, owner_id) is not None

    assert await repository.delete_for_user(row.id, owner_id) is True
    assert await repository.get_for_user(row.id, owner_id) is None


async def test_revoke_all_affects_only_the_named_user(db_session: AsyncSession) -> None:
    owner_id = await make_user(db_session, "owner")
    other_id = await make_user(db_session, "other")
    await make_session(db_session, owner_id)
    await make_session(db_session, owner_id)
    other_row = await make_session(db_session, other_id)

    repository = RefreshSessionRepository(db_session)
    assert await repository.revoke_all_for_user(owner_id) == 2
    assert await repository.list_active_for_user(owner_id) == []

    still_active = await repository.list_active_for_user(other_id)
    assert [row.id for row in still_active] == [other_row.id]


async def test_revoke_all_is_idempotent(db_session: AsyncSession) -> None:
    user_id = await make_user(db_session, "owner")
    await make_session(db_session, user_id)
    repository = RefreshSessionRepository(db_session)
    assert await repository.revoke_all_for_user(user_id) == 1
    assert await repository.revoke_all_for_user(user_id) == 0


async def test_expired_sessions_are_excluded_from_active_list(
    db_session: AsyncSession,
) -> None:
    user_id = await make_user(db_session, "owner")
    live = await make_session(db_session, user_id)
    await make_session(db_session, user_id, expires_in=timedelta(days=-1))

    active = await RefreshSessionRepository(db_session).list_active_for_user(user_id)
    assert [row.id for row in active] == [live.id]


async def test_lookup_by_token_hash_returns_revoked_rows(db_session: AsyncSession) -> None:
    """Reuse detection depends on being able to see an already-revoked session."""
    user_id = await make_user(db_session, "owner")
    row = await make_session(db_session, user_id)
    repository = RefreshSessionRepository(db_session)
    await repository.revoke(row)

    found = await repository.get_by_token_hash(row.token_hash)
    assert found is not None
    assert found.is_revoked is True


async def test_deleting_a_user_cascades_to_their_sessions(db_session: AsyncSession) -> None:
    """A deleted account must not leave a usable refresh token in the table."""
    user_id = await make_user(db_session, "owner")
    await make_session(db_session, user_id)

    users = UserRepository(db_session)
    user = await users.get_by_id(user_id)
    assert user is not None
    await users.delete(user)
    await users.flush()

    remaining = await db_session.execute(
        select(func.count()).select_from(RefreshSession).where(RefreshSession.user_id == user_id)
    )
    assert remaining.scalar_one() == 0
