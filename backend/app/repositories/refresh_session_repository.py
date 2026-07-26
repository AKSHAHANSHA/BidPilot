"""Refresh-session persistence — lookup by token hash, revocation, and rotation support."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, select, update

from app.models.refresh_session import RefreshSession
from app.repositories.base import OwnedRepository


class RefreshSessionRepository(OwnedRepository[RefreshSession]):
    model = RefreshSession
    owner_field = "user_id"

    def create(
        self,
        *,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
        user_agent: str | None,
        ip_hash: str | None,
    ) -> RefreshSession:
        session_row = RefreshSession(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            # Truncated here rather than trusting the client to send something reasonable.
            user_agent=user_agent[:256] if user_agent else None,
            ip_hash=ip_hash,
        )
        return self.add(session_row)

    async def get_by_token_hash(self, token_hash: str) -> RefreshSession | None:
        """Find a session by token hash, including revoked and expired ones.

        Revoked sessions are returned deliberately: distinguishing "this token never existed"
        from "this token was already used" is what makes reuse detection possible.
        """
        result = await self.session.execute(
            select(RefreshSession).where(RefreshSession.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def revoke(self, session_row: RefreshSession, *, now: datetime | None = None) -> None:
        if session_row.revoked_at is None:
            session_row.revoked_at = now or datetime.now(tz=UTC)
        await self.flush()

    async def revoke_all_for_user(self, user_id: uuid.UUID, *, now: datetime | None = None) -> int:
        """Revoke every live session for a user. Returns how many were affected.

        Used when a already-revoked token is presented, which suggests the token was captured:
        the safe response is to invalidate the whole family and force a fresh login.
        """
        result = await self.session.execute(
            update(RefreshSession)
            .where(RefreshSession.user_id == user_id, RefreshSession.revoked_at.is_(None))
            .values(revoked_at=now or datetime.now(tz=UTC))
        )
        await self.flush()
        return int(cast("CursorResult[Any]", result).rowcount)

    async def list_active_for_user(self, user_id: uuid.UUID) -> list[RefreshSession]:
        now = datetime.now(tz=UTC)
        result = await self.session.execute(
            select(RefreshSession)
            .where(
                RefreshSession.user_id == user_id,
                RefreshSession.revoked_at.is_(None),
                RefreshSession.expires_at > now,
            )
            .order_by(RefreshSession.created_at.desc())
        )
        return list(result.scalars().all())

    async def delete_expired(self, *, before: datetime | None = None) -> int:
        """Housekeeping for exhausted sessions. Not wired to a schedule in this phase."""
        cutoff = before or datetime.now(tz=UTC)
        rows = await self.session.execute(
            select(RefreshSession).where(RefreshSession.expires_at <= cutoff)
        )
        deleted = 0
        for row in rows.scalars().all():
            await self.session.delete(row)
            deleted += 1
        return deleted
