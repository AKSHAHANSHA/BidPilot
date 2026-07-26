"""Repository base classes.

`docs/04_API_AND_DATA_MODEL.md` §5 states the rule this module exists to enforce:

> Never fetch by tender ID and check ownership later in an unrelated layer.

:class:`OwnedRepository` makes the owner ID a *required parameter* of every read, update, and
delete. There is no method that fetches an owned row by ID alone, so a caller cannot forget
the check — the signature will not let them.
"""

from __future__ import annotations

import uuid
from abc import ABC
from typing import Any, ClassVar, cast

from sqlalchemy import ColumnElement, CursorResult, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.database import Base


class BaseRepository[ModelT: Base](ABC):
    """Shared persistence helpers for a single model.

    Repositories never commit. The unit of work is the request (or the job step), and
    `get_session` owns the transaction boundary — otherwise a service could not roll back a
    multi-table operation.
    """

    model: ClassVar[type[Any]]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        return entity

    async def flush(self) -> None:
        """Push pending changes so server defaults and constraint errors surface now."""
        await self.session.flush()

    async def commit_security_action(self) -> None:
        """Commit immediately, before an error response unwinds the request.

        The single documented exception to "repositories never commit". A revocation decided
        while rejecting a request — refresh-token reuse, for instance — must be durable even
        though the request then fails: `get_session` rolls back on exception, which would
        otherwise discard exactly the defensive action we just took.

        Never use this for ordinary writes; those belong to the request's unit of work.
        """
        await self.session.commit()

    async def delete(self, entity: ModelT) -> None:
        await self.session.delete(entity)


class OwnedRepository[ModelT: Base](BaseRepository[ModelT], ABC):
    """Base for models reachable only through their owning user.

    Subclasses set :attr:`owner_field` when the foreign key is not the default
    ``owner_user_id`` (``RefreshSession`` uses ``user_id``).
    """

    owner_field: ClassVar[str] = "owner_user_id"

    @classmethod
    def _owner_column(cls) -> InstrumentedAttribute[uuid.UUID]:
        column: InstrumentedAttribute[uuid.UUID] = getattr(cls.model, cls.owner_field)
        return column

    @classmethod
    def owned_by(cls, user_id: uuid.UUID) -> ColumnElement[bool]:
        """The ownership predicate, for services composing their own filtered queries."""
        return cls._owner_column() == user_id

    async def get_for_user(self, entity_id: uuid.UUID, user_id: uuid.UUID) -> ModelT | None:
        """Fetch one row, or None when it does not exist *or* belongs to someone else.

        Both cases return None on purpose: the API turns that into 404, which does not reveal
        whether another user's record with this ID exists.
        """
        result = await self.session.execute(
            select(self.model).where(self.model.id == entity_id, self.owned_by(user_id))
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ModelT]:
        result = await self.session.execute(
            select(self.model).where(self.owned_by(user_id)).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def count_for_user(self, user_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(self.model).where(self.owned_by(user_id))
        )
        return int(result.scalar_one())

    async def delete_for_user(self, entity_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Delete one owned row. Returns False when nothing matched."""
        result = await self.session.execute(
            delete(self.model).where(self.model.id == entity_id, self.owned_by(user_id))
        )
        # `execute` is typed as returning Result; a DELETE always yields a CursorResult.
        return bool(cast("CursorResult[Any]", result).rowcount)
