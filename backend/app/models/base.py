"""Shared column mixins for ORM models.

UUID primary keys are generated in Python rather than by the database so a service can build
an object graph (analysis → requirements → citations) and know every identifier before the
first flush.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    """Server-generated timestamps.

    `server_default`/`onupdate` keep these correct even for a bulk statement that bypasses
    the ORM's instance lifecycle.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
