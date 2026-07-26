"""Async SQLAlchemy engine, session factory, and declarative base.

The API and the worker share one async engine configuration and one driver (asyncpg).
Worker actors wrap `asyncio.run(...)` rather than introducing a second sync driver — see
`docs/08_ENGINEERING_DECISIONS.md`.

Engine construction is lazy so that importing this module has no side effects; unit tests
can build alternative `Settings` without opening a connection pool.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import MetaData, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import Settings, get_settings

#: Explicit constraint naming. Without it, Alembic autogenerate produces unnamed
#: constraints that later revisions cannot drop portably.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for every ORM model."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def create_engine(settings: Settings) -> AsyncEngine:
    """Build an engine without registering it as the process-wide engine."""
    return create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,  # a recycled connection must not surface as a request failure
        pool_size=5,
        max_overflow=5,
    )


def get_engine() -> AsyncEngine:
    """Return the process-wide engine, creating it on first use."""
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings())
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,  # response serialization happens after commit
            autoflush=False,
        )
    return _sessionmaker


async def dispose_engine() -> None:
    """Close the connection pool. Called from the application lifespan on shutdown."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a transactional session.

    Commits when the handler returns normally and rolls back on any exception, so a failed
    request can never leave a half-written analysis behind.
    """
    factory = get_sessionmaker()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def check_database() -> None:
    """Raise if PostgreSQL is unreachable. Used by the readiness probe."""
    engine = get_engine()
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
