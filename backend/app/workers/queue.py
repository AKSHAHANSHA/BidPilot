"""Job queue abstraction.

The service enqueues through this protocol so it never imports Dramatiq directly, and so tests
run the pipeline inline without a broker (`docs/08` D1). Two adapters:

* :class:`DramatiqJobQueue` — production: hands the message to Redis, the worker runs it.
* :class:`EagerJobQueue` — tests and the offline demo: runs the pipeline immediately against a
  provided session, so a full journey can be asserted without a running worker.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession


class JobQueue(Protocol):
    async def enqueue_analysis(self, analysis_id: uuid.UUID) -> None: ...


class DramatiqJobQueue:
    """Sends the analysis to the Redis broker for the worker to pick up.

    The caller must have committed the analysis row before enqueuing — the worker runs in a
    separate transaction and would not otherwise see it.
    """

    async def enqueue_analysis(self, analysis_id: uuid.UUID) -> None:
        from app.workers.broker import run_analysis_actor

        run_analysis_actor.send(str(analysis_id))


class EagerJobQueue:
    """Runs the pipeline inline against the given session. For tests and the offline demo.

    An optional `provider` is injected so tests drive extraction with a mock; without one, the
    AI stages report a configuration failure rather than reaching for a real key.
    """

    def __init__(self, session: AsyncSession, provider: object | None = None) -> None:
        self._session = session
        self._provider = provider

    async def enqueue_analysis(self, analysis_id: uuid.UUID) -> None:
        from app.ai.providers.base import LLMProvider
        from app.workers.pipeline import run_analysis

        provider: LLMProvider | None = self._provider  # type: ignore[assignment]
        await run_analysis(self._session, str(analysis_id), provider=provider)
