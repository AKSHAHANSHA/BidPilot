"""Logging must correlate requests and must never serialize secrets or document text."""

from __future__ import annotations

import json
import logging

import pytest

from app.core.logging import (
    REDACTED,
    ConsoleFormatter,
    ContextFilter,
    JsonFormatter,
    configure_logging,
    is_sensitive_key,
    request_id_var,
)


def make_record(**extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="analysis_stage_changed",
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    ContextFilter().filter(record)
    return record


def test_json_formatter_emits_one_parseable_object() -> None:
    record = make_record(tender_id="t-1", stage="verifying_citations")
    payload = json.loads(JsonFormatter().format(record))
    assert payload["level"] == "INFO"
    assert payload["logger"] == "app.test"
    assert payload["message"] == "analysis_stage_changed"
    assert payload["tender_id"] == "t-1"
    assert payload["stage"] == "verifying_citations"
    assert payload["timestamp"].endswith("+00:00")


def test_request_id_is_attached_from_context() -> None:
    token = request_id_var.set("abc123")
    try:
        payload = json.loads(JsonFormatter().format(make_record()))
    finally:
        request_id_var.reset(token)
    assert payload["request_id"] == "abc123"


@pytest.mark.parametrize(
    "key",
    [
        "password",
        "jwt_secret",
        "refresh_token",
        "openai_api_key",
        "authorization",
        "page_text",
        "document_text",
        "prompt_body",
    ],
)
def test_sensitive_keys_are_detected(key: str) -> None:
    assert is_sensitive_key(key) is True


def test_sensitive_extras_are_redacted_in_json_output() -> None:
    record = make_record(password="hunter2", page_text="THE BIDDER SHALL...", page_number=14)
    rendered = JsonFormatter().format(record)
    payload = json.loads(rendered)
    assert payload["password"] == REDACTED
    assert payload["page_text"] == REDACTED
    assert "hunter2" not in rendered
    assert "THE BIDDER SHALL" not in rendered
    # Non-sensitive provenance data is still logged; that is the point of the logs.
    assert payload["page_number"] == 14


def test_sensitive_extras_are_redacted_in_console_output() -> None:
    record = make_record(openai_api_key="sk-live-1234")
    rendered = ConsoleFormatter().format(record)
    assert "sk-live-1234" not in rendered
    assert REDACTED in rendered


def test_console_formatter_includes_message_and_level() -> None:
    rendered = ConsoleFormatter().format(make_record(analysis_id="a-9"))
    assert "analysis_stage_changed" in rendered
    assert "INFO" in rendered
    assert "analysis_id=a-9" in rendered


def test_configure_logging_installs_exactly_one_root_handler() -> None:
    configure_logging(level=logging.INFO, json_output=True)
    configure_logging(level=logging.INFO, json_output=True)  # idempotent
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, JsonFormatter)


def test_uvicorn_access_logger_is_silenced_to_avoid_duplicate_access_lines() -> None:
    # RequestContextMiddleware owns access logging; uvicorn's version would duplicate it
    # and reintroduce health-check noise.
    configure_logging(level=logging.INFO, json_output=False)
    assert logging.getLogger("uvicorn.access").level == logging.WARNING


def test_exception_traceback_goes_to_logs_not_message() -> None:
    try:
        raise ValueError("connection string user=admin password=hunter2")
    except ValueError:
        record = logging.LogRecord(
            name="app.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="failed",
            args=(),
            exc_info=True,
        )
        import sys

        record.exc_info = sys.exc_info()
    ContextFilter().filter(record)
    payload = json.loads(JsonFormatter().format(record))
    # Tracebacks are expected *in logs* — the API response is what must stay clean.
    assert "ValueError" in payload["exception"]
