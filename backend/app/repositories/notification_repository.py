"""Notification persistence.

Every method is scoped to the recipient, including the writes. `mark_read` takes the recipient
ID and puts it in the `WHERE` clause rather than loading by ID and checking afterwards: with
the ID alone, a caller could mark another user's notification read, which is a small harm but a
real one — it silently removes something from a stranger's unread badge.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, func, select, update

from app.domain.enums import NotificationType
from app.models.notification import Notification
from app.repositories.base import OwnedRepository


@dataclass(frozen=True, slots=True)
class NotificationDraft:
    """One notification to write.

    A draft rather than a bare `Notification` so `create_many` has a typed signature: several
    §9 events fan out to every applicant on a listing, and building the ORM objects in the
    service would put the column names back in the caller's hands.
    """

    recipient_user_id: uuid.UUID
    notification_type: NotificationType
    title: str
    body: str
    listing_id: uuid.UUID | None = None
    application_id: uuid.UUID | None = None
    screening_score: int | None = None


class NotificationRepository(OwnedRepository[Notification]):
    model = Notification
    owner_field = "recipient_user_id"

    async def list_for_recipient(
        self,
        recipient_user_id: uuid.UUID,
        *,
        unread_only: bool = False,
        limit: int,
        offset: int,
    ) -> tuple[list[Notification], int]:
        base = select(Notification).where(self.owned_by(recipient_user_id))
        if unread_only:
            base = base.where(Notification.read_at.is_(None))

        total = int(
            (
                await self.session.execute(select(func.count()).select_from(base.subquery()))
            ).scalar_one()
        )
        rows = await self.session.execute(
            base.order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars().all()), total

    async def unread_count(self, recipient_user_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(Notification)
            .where(self.owned_by(recipient_user_id), Notification.read_at.is_(None))
        )
        return int(result.scalar_one())

    async def mark_read(
        self,
        notification_id: uuid.UUID,
        recipient_user_id: uuid.UUID,
        *,
        now: datetime | None = None,
    ) -> bool:
        """Mark one notification read. False when it does not exist or belongs to someone else.

        `COALESCE` keeps the first read timestamp, which makes the call idempotent: a double
        click still matches a row, so the caller gets True and a 404 is reserved for the case
        that actually means "not yours".
        """
        result = await self.session.execute(
            update(Notification)
            .where(Notification.id == notification_id, self.owned_by(recipient_user_id))
            .values(read_at=func.coalesce(Notification.read_at, now or datetime.now(tz=UTC)))
        )
        return bool(cast("CursorResult[Any]", result).rowcount)

    async def mark_all_read(
        self, recipient_user_id: uuid.UUID, *, now: datetime | None = None
    ) -> int:
        """Clear the badge. Returns how many were still unread."""
        result = await self.session.execute(
            update(Notification)
            .where(self.owned_by(recipient_user_id), Notification.read_at.is_(None))
            .values(read_at=now or datetime.now(tz=UTC))
        )
        return int(cast("CursorResult[Any]", result).rowcount)

    def create(self, draft: NotificationDraft) -> Notification:
        notification = Notification(
            recipient_user_id=draft.recipient_user_id,
            type=draft.notification_type.value,
            title=draft.title,
            body=draft.body,
            listing_id=draft.listing_id,
            application_id=draft.application_id,
            screening_score=draft.screening_score,
        )
        return self.add(notification)

    def create_many(self, drafts: Sequence[NotificationDraft]) -> list[Notification]:
        """Stage a fan-out — "listing closed" reaches every applicant. Staged, not committed:
        the notifications belong to the same unit of work as the event that caused them, so a
        rolled-back close cannot leave users told about something that did not happen."""
        return [self.create(draft) for draft in drafts]
