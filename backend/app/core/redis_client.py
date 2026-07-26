"""Redis connection used by the readiness probe, the job broker, and rate limiting.

Redis is deliberately not the source of truth for job status; PostgreSQL is
(`docs/02_BACKEND_ARCHITECTURE.md` §4). This module only manages the connection.
"""

from __future__ import annotations

from redis.asyncio import Redis

from app.core.config import get_settings

_client: Redis | None = None


def get_redis() -> Redis:
    """Return the process-wide Redis client, creating it on first use."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
    return _client


async def close_redis() -> None:
    """Release the connection pool. Called from the application lifespan on shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
    _client = None


async def check_redis() -> None:
    """Raise if Redis is unreachable. Used by the readiness probe."""
    await get_redis().ping()
