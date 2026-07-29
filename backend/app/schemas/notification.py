"""Notification read schemas.

Read-only: rows are written by services when something happens to a listing or an
application, never by a client. Marking one read is a `POST` with no body, so there is no
write shape here either.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.domain.enums import NotificationType


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: NotificationType
    title: str
    body: str
    listing_id: Annotated[
        uuid.UUID | None,
        Field(
            description=(
                "Deep-link target. Null once the listing is gone — the notification loses its "
                "link rather than vanishing from the recipient's history."
            )
        ),
    ]
    application_id: uuid.UUID | None
    screening_score: Annotated[
        int | None,
        Field(ge=0, le=100, description="Denormalised score. Null for types that carry none."),
    ]
    read_at: datetime | None
    created_at: datetime

    @computed_field(description="Whether the recipient has opened this notification.")  # type: ignore[prop-decorator]
    @property
    def is_read(self) -> bool:
        # Derived from `read_at` rather than carried as a second column, so the badge and the
        # timestamp can never disagree.
        return self.read_at is not None


class NotificationCounts(BaseModel):
    """The header badge: how many are waiting, out of how many exist."""

    unread: Annotated[int, Field(ge=0)]
    total: Annotated[int, Field(ge=0)]
