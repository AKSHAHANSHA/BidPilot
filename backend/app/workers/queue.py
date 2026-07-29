"""Job queue abstraction.

The service enqueues through this protocol so it never imports Dramatiq directly, and so tests
run the pipeline inline without a broker (`docs/08` D1). Two adapters:

* :class:`DramatiqJobQueue` — production: hands the message to Redis, the worker runs it.
* :class:`EagerJobQueue` — tests, the offline demo, and any host that cannot run a second
  process (`JOB_EXECUTION=inline`, see `deploy/VERCEL.md`): runs the pipeline immediately
  against a provided session, so a full journey completes without a running worker.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession


class JobQueue(Protocol):
    async def enqueue_analysis(self, analysis_id: uuid.UUID) -> None: ...

    async def enqueue_screening(self, screening_id: uuid.UUID) -> None: ...


class DramatiqJobQueue:
    """Sends the job to the Redis broker for the worker to pick up.

    The caller must have committed the row before enqueuing — the worker runs in a separate
    transaction and would not otherwise see it.
    """

    async def enqueue_analysis(self, analysis_id: uuid.UUID) -> None:
        from app.workers.broker import run_analysis_actor

        run_analysis_actor.send(str(analysis_id))

    async def enqueue_screening(self, screening_id: uuid.UUID) -> None:
        # Imported lazily for the same reason as above: importing `broker` configures the global
        # Dramatiq broker, which the API process should only do when it actually enqueues.
        from app.workers.broker import run_screening_actor

        run_screening_actor.send(str(screening_id))


class EagerJobQueue:
    """Runs the pipeline inline against the given session, with no broker in between.

    Used by tests, by the offline demo, and by a deployment running `JOB_EXECUTION=inline`
    because its host has no worker process. In that last case the caller pays for the whole
    pipeline inside the request that submitted it — `get_job_queue` is where that trade-off is
    spelled out.

    An optional `provider` is injected so tests drive extraction with a mock. Without one the
    analysis pipeline's AI stages report a configuration failure rather than reaching for a real
    key; screening instead falls back to its deterministic classifier, because `docs/09` §4
    requires that pipeline to run on a deployment with no key at all.
    """

    def __init__(self, session: AsyncSession, provider: object | None = None) -> None:
        self._session = session
        self._provider = provider

    async def enqueue_analysis(self, analysis_id: uuid.UUID) -> None:
        from app.ai.providers.base import LLMProvider
        from app.workers.pipeline import run_analysis

        provider: LLMProvider | None = self._provider  # type: ignore[assignment]
        await run_analysis(self._session, str(analysis_id), provider=provider)

    async def enqueue_screening(self, screening_id: uuid.UUID) -> None:
        """Run the screening pipeline inline, on the caller's session.

        Storage, the OCR engine, and — when no mock is installed — the LLM provider are built
        from settings inside `run_screening`, so this genuinely screens: with no API key the
        provider factory returns the keyword provider and the pipeline classifies
        deterministically rather than failing (`docs/09` §4).
        """
        from app.ai.providers.base import LLMProvider
        from app.workers.screening_pipeline import run_screening

        provider: LLMProvider | None = self._provider  # type: ignore[assignment]
        await run_screening(self._session, str(screening_id), provider=provider)
