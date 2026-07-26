"""RFC 7807 problem details: the single error contract for the whole API.

Every failure the client can see is serialized through :class:`ProblemDetail`. Python
tracebacks, database messages, and LLM provider messages are logged but never sent to the
browser (`docs/02_BACKEND_ARCHITECTURE.md` §7).
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse, Response

from app.core.constants import PROBLEM_JSON_MEDIA_TYPE, PROBLEM_TYPE_BASE
from app.core.logging import get_logger, request_id_var

logger = get_logger(__name__)


class ProblemDetail(BaseModel):
    """RFC 7807 problem document, extended with `code` and `request_id`.

    `code` is the stable, machine-readable identifier the frontend switches on; `title` and
    `detail` are human-facing text that may be reworded without breaking clients.
    """

    type: str = Field(examples=[f"{PROBLEM_TYPE_BASE}/not-found"])
    title: str = Field(examples=["Resource not found"])
    status: int = Field(examples=[404])
    detail: str = Field(examples=["The requested tender does not exist."])
    instance: str | None = Field(default=None, examples=["/api/v1/tenders/8f0c.../documents"])
    code: str = Field(examples=["RESOURCE_NOT_FOUND"])
    request_id: str | None = Field(default=None)
    errors: list[dict[str, Any]] | None = Field(
        default=None,
        description="Field-level detail for validation failures.",
    )


class AppError(Exception):
    """Base class for every deliberately raised, client-visible application error.

    Services raise these; the API layer serializes them. Business logic therefore never
    imports FastAPI response classes.
    """

    status: int = HTTPStatus.INTERNAL_SERVER_ERROR
    code: str = "INTERNAL_ERROR"
    title: str = "Internal server error"
    slug: str = "internal-error"

    def __init__(self, detail: str, *, extra: dict[str, Any] | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.extra = extra or {}

    @property
    def type_uri(self) -> str:
        return f"{PROBLEM_TYPE_BASE}/{self.slug}"


class NotFoundError(AppError):
    """The resource does not exist, or is not owned by the authenticated user.

    Ownership failures deliberately reuse 404 so the API does not confirm the existence of
    another user's records.
    """

    status = HTTPStatus.NOT_FOUND
    code = "RESOURCE_NOT_FOUND"
    title = "Resource not found"
    slug = "not-found"


class ValidationProblem(AppError):
    """The request was well-formed but semantically unacceptable."""

    status = HTTPStatus.UNPROCESSABLE_ENTITY
    code = "REQUEST_INVALID"
    title = "Request invalid"
    slug = "request-invalid"


class ConflictError(AppError):
    """The request conflicts with current state, e.g. a duplicate email or document hash."""

    status = HTTPStatus.CONFLICT
    code = "RESOURCE_CONFLICT"
    title = "Conflict"
    slug = "conflict"


class AuthenticationError(AppError):
    """Credentials are missing, invalid, expired, or revoked.

    The detail stays generic on purpose: it must not reveal whether an account exists.
    """

    status = HTTPStatus.UNAUTHORIZED
    code = "NOT_AUTHENTICATED"
    title = "Not authenticated"
    slug = "not-authenticated"


class PermissionDeniedError(AppError):
    status = HTTPStatus.FORBIDDEN
    code = "PERMISSION_DENIED"
    title = "Permission denied"
    slug = "permission-denied"


class RateLimitedError(AppError):
    """Too many attempts. Carries the retry hint so the handler can set `Retry-After`."""

    status = HTTPStatus.TOO_MANY_REQUESTS
    code = "RATE_LIMITED"
    title = "Too many requests"
    slug = "rate-limited"

    def __init__(
        self, detail: str, *, retry_after_seconds: int, extra: dict[str, Any] | None = None
    ) -> None:
        super().__init__(detail, extra=extra)
        self.retry_after_seconds = retry_after_seconds


class ServiceUnavailableError(AppError):
    """A required dependency (database, Redis, provider) is unavailable."""

    status = HTTPStatus.SERVICE_UNAVAILABLE
    code = "SERVICE_DEPENDENCY_UNAVAILABLE"
    title = "Service dependency unavailable"
    slug = "service-unavailable"


def problem_response(
    *,
    status: int,
    code: str,
    title: str,
    detail: str,
    slug: str,
    request: Request | None = None,
    errors: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build a problem+json response."""
    problem = ProblemDetail(
        type=f"{PROBLEM_TYPE_BASE}/{slug}",
        title=title,
        status=status,
        detail=detail,
        instance=request.url.path if request is not None else None,
        code=code,
        request_id=request_id_var.get(),
        errors=errors,
    )
    return JSONResponse(
        status_code=status,
        content=problem.model_dump(exclude_none=True),
        media_type=PROBLEM_JSON_MEDIA_TYPE,
        headers=headers,
    )


def _slug_for_status(status: int) -> str:
    try:
        return HTTPStatus(status).phrase.lower().replace(" ", "-")
    except ValueError:
        return "error"


async def app_error_handler(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, AppError)  # noqa: S101 - handler is registered for this type only
    # Server-side faults deserve a stack trace; client mistakes do not.
    if exc.status >= HTTPStatus.INTERNAL_SERVER_ERROR:
        logger.error("application_error", exc_info=exc, extra={"code": exc.code, **exc.extra})
    else:
        logger.info(
            "application_error", extra={"code": exc.code, "status": exc.status, **exc.extra}
        )
    headers: dict[str, str] | None = None
    if isinstance(exc, RateLimitedError):
        headers = {"Retry-After": str(exc.retry_after_seconds)}
    return problem_response(
        status=exc.status,
        code=exc.code,
        title=exc.title,
        detail=exc.detail,
        slug=exc.slug,
        request=request,
        headers=headers,
    )


async def http_exception_handler(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101
    status = exc.status_code
    try:
        title = HTTPStatus(status).phrase
    except ValueError:
        title = "Error"
    detail = exc.detail if isinstance(exc.detail, str) else title
    return problem_response(
        status=status,
        code=f"HTTP_{status}",
        title=title,
        detail=detail,
        slug=_slug_for_status(status),
        request=request,
        headers=dict(exc.headers) if exc.headers else None,
    )


async def validation_exception_handler(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    # `input` and `ctx` are omitted deliberately: echoing the submitted value back would
    # leak a rejected password or API key into the response body and the client's logs.
    errors = [
        {
            "field": ".".join(str(part) for part in error["loc"]),
            "message": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors()
    ]
    logger.info("request_validation_failed", extra={"error_count": len(errors)})
    return problem_response(
        status=HTTPStatus.UNPROCESSABLE_ENTITY,
        code="REQUEST_VALIDATION_FAILED",
        title="Request validation failed",
        detail="The request body or parameters did not match the expected schema.",
        slug="request-validation-failed",
        request=request,
        errors=errors,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> Response:
    logger.exception("unhandled_exception", extra={"path": request.url.path})
    return problem_response(
        status=HTTPStatus.INTERNAL_SERVER_ERROR,
        code="INTERNAL_ERROR",
        title="Internal server error",
        detail=(
            "The request could not be completed because of an unexpected error. "
            "Quote the request_id when reporting this."
        ),
        slug="internal-error",
        request=request,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
