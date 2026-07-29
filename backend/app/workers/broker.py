"""Dramatiq broker and the worker actors.

Dramatiq over Celery (`docs/08` D1): Redis-native, minimal configuration. Each actor is a thin
synchronous wrapper that opens its own session and drives an async pipeline via
`asyncio.run(...)` — the worker never shares the API's engine or event loop (D2).

Importing this module configures the global broker, so it is imported only by the worker entry
point and by code that needs to enqueue. Tests use the eager queue and never touch Redis.
"""

from __future__ import annotations

import asyncio

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)

_settings = get_settings()
redis_broker = RedisBroker(url=_settings.redis_url)
dramatiq.set_broker(redis_broker)


@dramatiq.actor(max_retries=3, min_backoff=1000, max_backoff=60000)
def run_analysis_actor(analysis_id: str) -> None:
    """Worker entry point for one analysis. Retries are bounded by Dramatiq middleware.

    A fresh session per invocation, disposed afterwards, so a retry never reuses a connection
    bound to a dead event loop.
    """
    from app.ai.providers.openai_provider import OpenAIProvider
    from app.core.database import dispose_engine, get_sessionmaker
    from app.workers.pipeline import run_analysis

    async def _run() -> None:
        provider = OpenAIProvider(_settings)
        factory = get_sessionmaker()
        async with factory() as session:
            await run_analysis(session, analysis_id, provider=provider)
        await dispose_engine()

    asyncio.run(_run())


@dramatiq.actor(max_retries=3, min_backoff=1000, max_backoff=60000)
def run_screening_actor(screening_id: str) -> None:
    """Worker entry point for one application screening (`docs/09` §4).

    No provider is passed: `run_screening` builds one through `app/ai/providers/factory.py`, so
    a deployment with no OpenAI key still screens — deterministically, and saying so in the logs
    — instead of failing every submission at the classifier.
    """
    from app.core.database import dispose_engine, get_sessionmaker
    from app.workers.screening_pipeline import run_screening

    async def _run() -> None:
        factory = get_sessionmaker()
        async with factory() as session:
            await run_screening(session, screening_id, settings=_settings)
        await dispose_engine()

    asyncio.run(_run())


def configure_worker_logging() -> None:
    configure_logging(level=_settings.log_level_number, json_output=not _settings.is_development)
