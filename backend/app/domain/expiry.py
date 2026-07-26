"""Derived expiry state for company evidence.

The state is **calculated, never stored**. A stored "expiring soon" becomes wrong simply
because time passed, with no write to trigger an update — the classic stale-derived-value bug.

Two implementations must agree: :func:`derive_expiry_state` for a loaded record, and
:func:`expiry_state_filter` for filtering in SQL without loading every row. They are tested
against each other over a matrix of dates and statuses, because a divergence would mean the
list endpoint and the detail endpoint disagree about the same record.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import ColumnElement, and_, or_
from sqlalchemy.orm import InstrumentedAttribute

from app.domain.enums import ExpiryState, VerificationStatus

#: Precedence, highest first. Documented here because the order is a policy decision:
#:
#: 1. **expired** — a date in the past is an unambiguous fact, whether or not the user has
#:    confirmed the document. An expired licence blocks a bid regardless of bookkeeping.
#: 2. **unverified** — anything not `verified` (including `rejected`) cannot be relied on, so
#:    its dates are not worth interpreting further. The raw `verification_status` field still
#:    distinguishes "not yet checked" from "rejected".
#: 3. **no_expiry** — verified and has no expiry date at all.
#: 4. **expiring_soon** — verified and within the configured threshold.
#: 5. **active** — verified and comfortably in date.
PRECEDENCE = (
    ExpiryState.EXPIRED,
    ExpiryState.UNVERIFIED,
    ExpiryState.NO_EXPIRY,
    ExpiryState.EXPIRING_SOON,
    ExpiryState.ACTIVE,
)


def derive_expiry_state(
    *,
    expiry_date: date | None,
    verification_status: str,
    today: date,
    threshold_days: int,
) -> ExpiryState:
    """Classify one evidence record. Pure; no I/O, no clock access."""
    if expiry_date is not None and expiry_date < today:
        return ExpiryState.EXPIRED

    if verification_status != VerificationStatus.VERIFIED:
        return ExpiryState.UNVERIFIED

    if expiry_date is None:
        return ExpiryState.NO_EXPIRY

    if expiry_date <= today + timedelta(days=threshold_days):
        return ExpiryState.EXPIRING_SOON

    return ExpiryState.ACTIVE


def days_until_expiry(*, expiry_date: date | None, today: date) -> int | None:
    """Signed day count: negative when already expired, None when there is no expiry."""
    if expiry_date is None:
        return None
    return (expiry_date - today).days


def expiry_state_filter(
    state: ExpiryState,
    *,
    expiry_column: InstrumentedAttribute[date | None],
    status_column: InstrumentedAttribute[str],
    today: date,
    threshold_days: int,
) -> ColumnElement[bool]:
    """The SQL equivalent of :func:`derive_expiry_state` for a single state.

    Each branch encodes the same precedence: a later state must also exclude the conditions
    claimed by every earlier one.
    """
    horizon = today + timedelta(days=threshold_days)
    not_expired = or_(expiry_column.is_(None), expiry_column >= today)
    verified = status_column == VerificationStatus.VERIFIED.value

    match state:
        case ExpiryState.EXPIRED:
            return and_(expiry_column.is_not(None), expiry_column < today)
        case ExpiryState.UNVERIFIED:
            return and_(not_expired, status_column != VerificationStatus.VERIFIED.value)
        case ExpiryState.NO_EXPIRY:
            return and_(verified, expiry_column.is_(None))
        case ExpiryState.EXPIRING_SOON:
            # `>= today` matters: without it this branch would also claim expired records,
            # contradicting the precedence above.
            return and_(
                verified,
                expiry_column.is_not(None),
                expiry_column >= today,
                expiry_column <= horizon,
            )
        case ExpiryState.ACTIVE:
            return and_(verified, expiry_column.is_not(None), expiry_column > horizon)

    raise ValueError(f"Unhandled expiry state: {state}")
