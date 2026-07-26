"""Inbound request IDs are echoed, but only after being bounded and sanitized."""

from __future__ import annotations

import pytest

from app.api.middleware import is_low_noise_path, sanitize_request_id
from app.core.constants import REQUEST_ID_MAX_LENGTH


def test_missing_id_is_generated() -> None:
    generated = sanitize_request_id(None)
    assert len(generated) == 32
    assert generated != sanitize_request_id(None)


def test_valid_id_is_preserved() -> None:
    assert sanitize_request_id("req-9f3a_01") == "req-9f3a_01"


def test_blank_id_is_replaced() -> None:
    assert sanitize_request_id("   ") != "   "


def test_overlong_id_is_truncated_then_accepted() -> None:
    long_id = "a" * (REQUEST_ID_MAX_LENGTH + 40)
    assert sanitize_request_id(long_id) == "a" * REQUEST_ID_MAX_LENGTH


@pytest.mark.parametrize(
    "hostile",
    [
        "abc\r\nX-Injected: 1",  # header injection
        "abc def",
        "<script>alert(1)</script>",
        "id;rm -rf /",
        "ünïcode",
    ],
)
def test_hostile_id_is_discarded_not_echoed(hostile: str) -> None:
    sanitized = sanitize_request_id(hostile)
    assert sanitized != hostile
    assert len(sanitized) == 32
    assert sanitized.isalnum()


@pytest.mark.parametrize(
    "path",
    ["/health/live", "/health/ready", "/api/v1/health/live", "/api/v1/health/ready"],
)
def test_health_polling_is_demoted_on_both_mount_points(path: str) -> None:
    # The routes are mounted unprefixed and under API_V1_PREFIX; continuous polling of
    # either must not drown out real request logs.
    assert is_low_noise_path(path) is True


@pytest.mark.parametrize("path", ["/api/v1/tenders", "/api/v1/health/ready/extra", "/"])
def test_real_traffic_is_logged_at_info(path: str) -> None:
    assert is_low_noise_path(path) is False
