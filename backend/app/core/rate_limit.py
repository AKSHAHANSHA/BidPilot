"""Redis fixed-window rate limiting for authentication endpoints.

Deliberately simple: `INCR` plus `EXPIRE` on a bucket keyed by window. A sliding-window or
token-bucket implementation would be more precise at the boundary, but this is enough to blunt
credential stuffing against a portfolio demo, and it is easy to reason about — which matters
more than precision here.

**Fail-open on Redis errors.** If Redis is unreachable, requests are allowed and a warning is
logged. Failing closed would turn a cache outage into a total login outage; the database
remains the authority on whether credentials are valid either way.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from redis.exceptions import RedisError

from app.core.logging import get_logger
from app.core.redis_client import get_redis

logger = get_logger(__name__)

KEY_PREFIX = "ratelimit"


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after_seconds: int

    @property
    def exceeded(self) -> bool:
        return not self.allowed


class RateLimiter:
    """Counts attempts per (scope, identity, window)."""

    def __init__(self, *, limit: int, window_seconds: int, scope: str) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.scope = scope

    def _key(self, identity: str, *, now: float) -> str:
        window_index = int(now // self.window_seconds)
        return f"{KEY_PREFIX}:{self.scope}:{identity}:{window_index}"

    async def hit(self, identity: str, *, now: float | None = None) -> RateLimitDecision:
        """Record an attempt and report whether it is allowed."""
        timestamp = now if now is not None else time.time()
        key = self._key(identity, now=timestamp)
        seconds_left = self.window_seconds - int(timestamp % self.window_seconds)

        try:
            redis = get_redis()
            pipeline = redis.pipeline()
            pipeline.incr(key)
            # Set the TTL on every hit; a bucket that lost its expiry would block forever.
            pipeline.expire(key, self.window_seconds)
            count = int((await pipeline.execute())[0])
        except RedisError as exc:
            logger.warning(
                "rate_limit_unavailable",
                extra={"scope": self.scope, "error_type": type(exc).__name__},
            )
            return RateLimitDecision(allowed=True, remaining=self.limit, retry_after_seconds=0)

        if count > self.limit:
            logger.warning(
                "rate_limit_exceeded",
                extra={"scope": self.scope, "attempts": count, "limit": self.limit},
            )
            return RateLimitDecision(
                allowed=False, remaining=0, retry_after_seconds=max(seconds_left, 1)
            )

        return RateLimitDecision(
            allowed=True,
            remaining=max(self.limit - count, 0),
            retry_after_seconds=0,
        )

    async def reset(self, identity: str, *, now: float | None = None) -> None:
        """Clear the current bucket, e.g. after a successful login."""
        timestamp = now if now is not None else time.time()
        try:
            await get_redis().delete(self._key(identity, now=timestamp))
        except RedisError as exc:
            logger.warning(
                "rate_limit_reset_failed",
                extra={"scope": self.scope, "error_type": type(exc).__name__},
            )
