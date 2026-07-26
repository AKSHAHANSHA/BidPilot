"""Application factory and ASGI entry point.

Configuration is loaded before anything else so a misconfigured process dies at startup
with a precise message instead of serving traffic in an unknown state.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.errors import register_exception_handlers
from app.api.middleware import RequestContextMiddleware
from app.api.v1 import api_router
from app.api.v1 import health as health_module
from app.core.config import Settings, get_settings
from app.core.constants import REQUEST_ID_HEADER
from app.core.database import dispose_engine
from app.core.logging import configure_logging, get_logger
from app.core.redis_client import close_redis

logger = get_logger(__name__)

DESCRIPTION = """
BidPilot UAE turns an unstructured tender PDF into a reviewable decision workspace:
page-aware extraction, schema-constrained requirement extraction, verified citations,
deterministic readiness scoring, and human review.

Uploaded document content is treated as untrusted evidence, never as instructions.
AI output is advisory; the readiness score is calculated in Python, not by a model.
""".strip()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    logger.info(
        "application_startup",
        extra={
            "environment": settings.app_env,
            "version": __version__,
            "storage_backend": settings.storage_backend,
            "prompt_version": settings.prompt_version,
            "scoring_version": settings.scoring_version,
        },
    )
    try:
        yield
    finally:
        await dispose_engine()
        await close_redis()
        logger.info("application_shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application."""
    settings = settings or get_settings()
    configure_logging(level=settings.log_level_number, json_output=not settings.is_development)
    settings.ensure_directories()

    app = FastAPI(
        title=settings.app_name,
        description=DESCRIPTION,
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.state.settings = settings

    # Order matters. `add_middleware` prepends, so CORS ends up outermost and can attach
    # its headers to the problem responses produced by RequestContextMiddleware — without
    # that, a browser cannot read the body of a 500.
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,  # the Phase 1 refresh token travels in an HttpOnly cookie
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
    )

    register_exception_handlers(app)

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    # Unprefixed aliases so hosting platforms can probe a stable path regardless of
    # API_V1_PREFIX. Hidden from the schema to keep one documented path per operation.
    app.include_router(health_module.router, include_in_schema=False)

    return app


app = create_app()
