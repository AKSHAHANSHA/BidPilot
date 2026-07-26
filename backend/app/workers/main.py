"""Worker entry point.

Run with:  dramatiq app.workers.main

Importing `broker` configures the global Dramatiq broker and registers the actor. This module
is the single import Dramatiq needs to discover the worker's tasks.
"""

from __future__ import annotations

from app.workers.broker import configure_worker_logging, run_analysis_actor

configure_worker_logging()

__all__ = ["run_analysis_actor"]
