"""Expiry state derivation and its SQL twin."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.domain.enums import ExpiryState, VerificationStatus
from app.domain.expiry import days_until_expiry, derive_expiry_state

TODAY = date(2026, 7, 26)
THRESHOLD = 60

VERIFIED = VerificationStatus.VERIFIED.value
UNVERIFIED = VerificationStatus.UNVERIFIED.value
REJECTED = VerificationStatus.REJECTED.value


def state(expiry: date | None, status: str = VERIFIED, threshold: int = THRESHOLD) -> ExpiryState:
    return derive_expiry_state(
        expiry_date=expiry,
        verification_status=status,
        today=TODAY,
        threshold_days=threshold,
    )


# --- The five states ----------------------------------------------------------------------


def test_verified_and_far_from_expiry_is_active() -> None:
    assert state(TODAY + timedelta(days=THRESHOLD + 1)) is ExpiryState.ACTIVE


def test_verified_and_inside_the_window_is_expiring_soon() -> None:
    assert state(TODAY + timedelta(days=THRESHOLD - 1)) is ExpiryState.EXPIRING_SOON


def test_verified_with_no_expiry_date_is_no_expiry() -> None:
    assert state(None) is ExpiryState.NO_EXPIRY


def test_past_expiry_is_expired() -> None:
    assert state(TODAY - timedelta(days=1)) is ExpiryState.EXPIRED


def test_unverified_evidence_in_date_is_unverified() -> None:
    assert state(TODAY + timedelta(days=365), status=UNVERIFIED) is ExpiryState.UNVERIFIED


def test_unverified_without_an_expiry_date_is_unverified_not_no_expiry() -> None:
    assert state(None, status=UNVERIFIED) is ExpiryState.UNVERIFIED


def test_rejected_evidence_is_reported_as_unverified() -> None:
    """Rejected is not usable either. The raw `verification_status` still distinguishes them."""
    assert state(TODAY + timedelta(days=365), status=REJECTED) is ExpiryState.UNVERIFIED


# --- Boundaries -----------------------------------------------------------------------------


def test_expiring_today_is_not_yet_expired() -> None:
    # A licence valid through today is still valid today.
    assert state(TODAY) is ExpiryState.EXPIRING_SOON


def test_the_threshold_day_itself_counts_as_expiring_soon() -> None:
    assert state(TODAY + timedelta(days=THRESHOLD)) is ExpiryState.EXPIRING_SOON


def test_one_day_past_the_threshold_is_active() -> None:
    assert state(TODAY + timedelta(days=THRESHOLD + 1)) is ExpiryState.ACTIVE


@pytest.mark.parametrize("threshold", [1, 30, 60, 90, 365])
def test_threshold_is_honoured_as_configured(threshold: int) -> None:
    inside = TODAY + timedelta(days=threshold)
    outside = TODAY + timedelta(days=threshold + 1)
    assert state(inside, threshold=threshold) is ExpiryState.EXPIRING_SOON
    assert state(outside, threshold=threshold) is ExpiryState.ACTIVE


# --- Precedence -----------------------------------------------------------------------------


def test_expired_beats_unverified() -> None:
    """An expired date is an unambiguous fact regardless of verification bookkeeping."""
    assert state(TODAY - timedelta(days=1), status=UNVERIFIED) is ExpiryState.EXPIRED
    assert state(TODAY - timedelta(days=1), status=REJECTED) is ExpiryState.EXPIRED


def test_unverified_beats_expiring_soon_and_no_expiry() -> None:
    # Dates on unverified evidence are not worth interpreting further.
    assert state(TODAY + timedelta(days=5), status=UNVERIFIED) is ExpiryState.UNVERIFIED
    assert state(None, status=UNVERIFIED) is ExpiryState.UNVERIFIED


# --- Day counting ---------------------------------------------------------------------------


def test_days_until_expiry_is_positive_before_and_negative_after() -> None:
    assert days_until_expiry(expiry_date=TODAY + timedelta(days=45), today=TODAY) == 45
    assert days_until_expiry(expiry_date=TODAY - timedelta(days=3), today=TODAY) == -3


def test_days_until_expiry_is_zero_on_the_expiry_day() -> None:
    assert days_until_expiry(expiry_date=TODAY, today=TODAY) == 0


def test_days_until_expiry_is_none_without_a_date() -> None:
    assert days_until_expiry(expiry_date=None, today=TODAY) is None


# --- Exhaustiveness --------------------------------------------------------------------------


def test_every_state_is_reachable() -> None:
    """A state nothing can produce would be dead weight in the API contract and the UI."""
    produced = {
        state(TODAY + timedelta(days=365)),
        state(TODAY + timedelta(days=10)),
        state(None),
        state(TODAY - timedelta(days=10)),
        state(None, status=UNVERIFIED),
    }
    assert produced == set(ExpiryState)
