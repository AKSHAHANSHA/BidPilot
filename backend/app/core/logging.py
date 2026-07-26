"""Structured logging with request correlation and sensitive-value redaction.

Two formatters share one pipeline: readable console output locally, single-line JSON in
deployed environments. Both carry the request ID (and user ID once authentication exists)
so an API log line, a worker log line, and an error response can be tied together.

`docs/02_BACKEND_ARCHITECTURE.md` §8 forbids logging passwords, tokens, API keys, full
uploaded text, or complete prompts containing private documents. Convention alone is not
enough over a long build, so the formatter redacts denylisted keys before serialization.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)

REDACTED = "[redacted]"

#: Substrings that mark a value as unsafe to log. Matched case-insensitively against the
#: name of any structured extra passed to a logger.
SENSITIVE_KEY_MARKERS: tuple[str, ...] = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "credential",
    "page_text",
    "document_text",
    "raw_text",
    "prompt_body",
)

#: Attributes present on every LogRecord. Anything else was passed via `extra=` and is
#: treated as structured context.
_STANDARD_RECORD_ATTRS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)

_CONTEXT_ATTRS = ("request_id", "user_id")


def is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in SENSITIVE_KEY_MARKERS)


def _extract_context(record: logging.LogRecord) -> dict[str, Any]:
    """Collect structured extras from a record, redacting anything sensitive."""
    context: dict[str, Any] = {}
    for key, value in record.__dict__.items():
        if key in _STANDARD_RECORD_ATTRS or key in _CONTEXT_ATTRS or key.startswith("_"):
            continue
        context[key] = REDACTED if is_sensitive_key(key) else value
    return context


class ContextFilter(logging.Filter):
    """Attach the current request and user IDs to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.user_id = user_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line, suitable for a hosted log aggregator."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
            "user_id": getattr(record, "user_id", None),
        }
        payload.update(_extract_context(record))
        if record.exc_info:
            # The traceback belongs in logs only; it is never serialized into a response.
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Compact human-readable output for local development."""

    def format(self, record: logging.LogRecord) -> str:
        stamp = datetime.fromtimestamp(record.created, tz=UTC).strftime("%H:%M:%S")
        request_id = getattr(record, "request_id", None)
        correlation = f" [{request_id[:8]}]" if request_id else ""
        context = _extract_context(record)
        suffix = " " + " ".join(f"{k}={v}" for k, v in context.items()) if context else ""
        line = f"{stamp} {record.levelname:<8}{correlation} {record.name}: {record.getMessage()}"
        if suffix:
            line += suffix
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def configure_logging(*, level: int = logging.INFO, json_output: bool = False) -> None:
    """Install a single root handler. Safe to call more than once."""
    formatter: logging.Formatter = JsonFormatter() if json_output else ConsoleFormatter()

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(ContextFilter())

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)

    # Uvicorn installs its own handlers; route them through ours so every line carries the
    # request ID and the same format.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True

    # `RequestContextMiddleware` already emits one structured access line per request, with
    # the request ID, status, and latency. Uvicorn's access logger would duplicate it with
    # less detail and would re-add the health-check noise the middleware deliberately
    # demotes to DEBUG. Its level is raised rather than disabled so genuine warnings survive.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    # SQLAlchemy's engine logger is very chatty at INFO; opt in deliberately when needed.
    logging.getLogger("sqlalchemy.engine").setLevel(max(level, logging.WARNING))


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
