"""Password-reset token persistence.

Deliberately shaped like `RefreshSessionRepository`, because the security properties are the
same: lookup is by token *hash* only, so a database read never yields a usable link, and
spending or superseding a token is an UPDATE the caller cannot forget to scope.

`get_by_token_hash` returns used and expired tokens too. The caller needs the distinction —
"never existed", "already spent", and "expired" are three different situations — and answering
all of them with None would push that decision into a second query.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, func, select, update

from app.models.password_reset import PasswordResetToken
from app.repositories.base import OwnedRepository


class PasswordResetTokenRepository(OwnedRepository[PasswordResetToken]):
    model = PasswordResetToken
    owner_field = "user_id"

    def create(
        self,
        *,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
        requested_ip_hash: str | None = None,
    ) -> PasswordResetToken:
        token = PasswordResetToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            requested_ip_hash=requested_ip_hash,
        )
        return self.add(token)

    async def get_by_token_hash(self, token_hash: str) -> PasswordResetToken | None:
        result = await self.session.execute(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def mark_used(self, token: PasswordResetToken, *, now: datetime | None = None) -> None:
        """Spend the token. Guarded so a replay cannot overwrite the original timestamp, which
        is the only record of when the reset actually happened."""
        if token.used_at is None:
            token.used_at = now or datetime.now(tz=UTC)
        await self.flush()

    async def invalidate_for_user(self, user_id: uuid.UUID, *, now: datetime | None = None) -> int:
        """Retire every live token for a user. Returns how many were affected.

        Called when a reset is issued and again when one is consumed: two outstanding links for
        the same account means an attacker who triggered a reset still holds a working one after
        the real owner completes theirs.
        """
        moment = now or datetime.now(tz=UTC)
        result = await self.session.execute(
            update(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user_id,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.expires_at > moment,
            )
            .values(used_at=moment)
        )
        await self.flush()
        return int(cast("CursorResult[Any]", result).rowcount)

    async def count_recent_for_user(self, user_id: uuid.UUID, *, since: datetime) -> int:
        """How many tokens this account has been issued inside the window.

        The rate limit in `docs/09` §3.2 is per email+IP; this is the per-account half of it,
        and it is the half that survives a client rotating addresses.
        """
        result = await self.session.execute(
            select(func.count())
            .select_from(PasswordResetToken)
            .where(self.owned_by(user_id), PasswordResetToken.created_at >= since)
        )
        return int(result.scalar_one())

    async def delete_expired(self, *, before: datetime | None = None) -> int:
        """Housekeeping. Spent and expired tokens have no further purpose."""
        cutoff = before or datetime.now(tz=UTC)
        rows = await self.session.execute(
            select(PasswordResetToken).where(PasswordResetToken.expires_at <= cutoff)
        )
        deleted = 0
        for row in rows.scalars().all():
            await self.session.delete(row)
            deleted += 1
        return deleted
