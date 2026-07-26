"""Request correlation, access logging, and last-resort error containment.

Implemented as pure ASGI middleware rather than `BaseHTTPMiddleware` for one concrete
reason: Starlette's `ServerErrorMiddleware` sits *outside* the user middleware stack, so an
unhandled exception would otherwise bypass this layer and produce a 500 with no
`X-Request-ID` header and no access log line. Catching `Exception` here keeps every
response — success or failure — correlated and logged the same way.
"""

from __future__ import annotations

import time
import uuid
from http import HTTPStatus

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.errors import problem_response
from app.core.constants import REQUEST_ID_HEADER, REQUEST_ID_MAX_LENGTH
from app.core.logging import get_logger, request_id_var, user_id_var

logger = get_logger(__name__)

_ID_SAFE_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")

#: Health endpoints are polled continuously by hosting platforms and by the frontend's
#: status view; logging them at INFO buries everything else. Matched as suffixes because the
#: same routes are mounted both unprefixed and under API_V1_PREFIX.
_LOW_NOISE_PATH_SUFFIXES = ("/health/live", "/health/ready")


def is_low_noise_path(path: str) -> bool:
    return path.endswith(_LOW_NOISE_PATH_SUFFIXES)


def sanitize_request_id(raw: str | None) -> str:
    """Return a safe request ID, generating one when the inbound value is unusable.

    The value is echoed into a response header and into logs, so an unbounded or
    control-character-laden client value is never accepted as-is.
    """
    if not raw:
        return uuid.uuid4().hex
    candidate = raw.strip()[:REQUEST_ID_MAX_LENGTH]
    if not candidate or any(char not in _ID_SAFE_CHARS for char in candidate):
        return uuid.uuid4().hex
    return candidate


class RequestContextMiddleware:
    """Bind a request ID to the request, echo it, log the outcome, contain failures."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.decode("latin-1").lower(): value for key, value in scope["headers"]}
        inbound = headers.get(REQUEST_ID_HEADER.lower())
        request_id = sanitize_request_id(inbound.decode("latin-1") if inbound else None)

        id_token = request_id_var.set(request_id)
        user_token = user_id_var.set(None)
        started = time.perf_counter()
        status_code = HTTPStatus.INTERNAL_SERVER_ERROR.value
        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                message["headers"] = [
                    *message.get("headers", []),
                    (REQUEST_ID_HEADER.encode("latin-1"), request_id.encode("latin-1")),
                ]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            logger.exception("unhandled_exception", extra={"path": scope.get("path")})
            if not response_started:
                # A partially streamed response cannot be replaced; only log in that case.
                response = problem_response(
                    status=HTTPStatus.INTERNAL_SERVER_ERROR,
                    code="INTERNAL_ERROR",
                    title="Internal server error",
                    detail=(
                        "The request could not be completed because of an unexpected error. "
                        "Quote the request_id when reporting this."
                    ),
                    slug="internal-error",
                )
                response.headers[REQUEST_ID_HEADER] = request_id
                await response(scope, receive, send)
            status_code = HTTPStatus.INTERNAL_SERVER_ERROR.value
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            path = scope.get("path", "")
            log = logger.debug if is_low_noise_path(path) else logger.info
            log(
                "http_request",
                extra={
                    "method": scope.get("method"),
                    "path": path,
                    "status": status_code,
                    "duration_ms": duration_ms,
                },
            )
            request_id_var.reset(id_token)
            user_id_var.reset(user_token)
