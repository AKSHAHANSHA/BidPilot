"""Worker entry point.

Run with:  dramatiq app.workers.main

Importing `broker` configures the global Dramatiq broker and registers the actors. This module
is the single import Dramatiq needs to discover the worker's tasks, so every actor has to be
named here — one worker process serves both the analysis and the screening jobs.
"""

from __future__ import annotations

from app.workers.broker import configure_worker_logging, run_analysis_actor, run_screening_actor

configure_worker_logging()

__all__ = ["run_analysis_actor", "run_screening_actor"]
