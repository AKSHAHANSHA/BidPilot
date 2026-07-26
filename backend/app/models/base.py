"""Shared column mixins for ORM models.

UUID primary keys are generated in Python rather than by the database so a service can build
an object graph (analysis → requirements → citations) and know every identifier before the
first flush.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    """Server-generated timestamps.

    `server_default`/`onupdate` keep these correct even for a bulk statement that bypasses
    the ORM's instance lifecycle.
    """

    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, Any]:
        """Fetch server-generated timestamps inline via RETURNING.

        Without this, SQLAlchemy leaves `updated_at` **expired** after an UPDATE and reloads it
        lazily on next access. If that access happens in synchronous code — a response
        serializer, for instance — the implicit SELECT raises `MissingGreenlet`, because async
        IO cannot be driven from a sync call stack. Turning a 200 into a 500 is a high price for
        one timestamp, so the value is returned by the same statement that wrote it.
        """
        return {"eager_defaults": True}

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
