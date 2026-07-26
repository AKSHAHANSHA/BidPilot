"""The SQL expiry filter and the Python derivation must agree, row for row.

Two implementations of one rule is a standing invitation to drift. If they diverge, the list
endpoint and the detail endpoint report different states for the same evidence — a bug that is
invisible in isolation and obvious to a user. So the agreement is asserted directly against
PostgreSQL over the full matrix of date positions and verification statuses.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ExpiryState, VerificationStatus
from app.domain.expiry import derive_expiry_state, expiry_state_filter
from app.models.company_evidence import CompanyEvidence
from tests.integration.factories import make_profile, make_user

pytestmark = pytest.mark.integration

THRESHOLD = 60

#: Every meaningful position relative to today and the threshold, including the boundaries.
DATE_OFFSETS: tuple[int | None, ...] = (
    None,
    -400,
    -1,
    0,
    1,
    THRESHOLD - 1,
    THRESHOLD,
    THRESHOLD + 1,
    400,
)


async def _seed_matrix(
    session: AsyncSession, *, owner_id: uuid.UUID, profile_id: uuid.UUID, today: date
) -> None:
    for offset in DATE_OFFSETS:
        for status in VerificationStatus:
            session.add(
                CompanyEvidence(
                    owner_user_id=owner_id,
                    company_profile_id=profile_id,
                    title=f"offset={offset} status={status.value}",
                    category="certification",
                    description="Matrix row for the expiry-agreement test.",
                    expiry_date=None if offset is None else today + timedelta(days=offset),
                    verification_status=status.value,
                    tags=[],
                )
            )
    await session.flush()


@pytest.fixture
async def matrix(db_session: AsyncSession) -> tuple[uuid.UUID, date]:
    today = date(2026, 7, 26)
    user = await make_user(db_session)
    profile = await make_profile(db_session, user.id)
    await _seed_matrix(db_session, owner_id=user.id, profile_id=profile.id, today=today)
    return user.id, today


@pytest.mark.parametrize("state", list(ExpiryState))
async def test_sql_filter_matches_python_derivation(
    db_session: AsyncSession, matrix: tuple[uuid.UUID, date], state: ExpiryState
) -> None:
    owner_id, today = matrix

    rows = (
        (
            await db_session.execute(
                select(CompanyEvidence).where(CompanyEvidence.owner_user_id == owner_id)
            )
        )
        .scalars()
        .all()
    )

    expected = {
        row.id
        for row in rows
        if derive_expiry_state(
            expiry_date=row.expiry_date,
            verification_status=row.verification_status,
            today=today,
            threshold_days=THRESHOLD,
        )
        is state
    }

    filtered = (
        (
            await db_session.execute(
                select(CompanyEvidence).where(
                    CompanyEvidence.owner_user_id == owner_id,
                    expiry_state_filter(
                        state,
                        expiry_column=CompanyEvidence.expiry_date,
                        status_column=CompanyEvidence.verification_status,
                        today=today,
                        threshold_days=THRESHOLD,
                    ),
                )
            )
        )
        .scalars()
        .all()
    )

    assert {row.id for row in filtered} == expected, (
        f"SQL and Python disagree for {state.value}: "
        f"sql_only={sorted(str(r.id) for r in filtered if r.id not in expected)}, "
        f"python_only={len(expected - {r.id for r in filtered})}"
    )


async def test_the_states_partition_every_row_exactly_once(
    db_session: AsyncSession, matrix: tuple[uuid.UUID, date]
) -> None:
    """Each row belongs to exactly one state — no gaps, no double counting."""
    owner_id, today = matrix
    total = len(DATE_OFFSETS) * len(VerificationStatus)

    seen: set[uuid.UUID] = set()
    for state in ExpiryState:
        rows = (
            (
                await db_session.execute(
                    select(CompanyEvidence.id).where(
                        CompanyEvidence.owner_user_id == owner_id,
                        expiry_state_filter(
                            state,
                            expiry_column=CompanyEvidence.expiry_date,
                            status_column=CompanyEvidence.verification_status,
                            today=today,
                            threshold_days=THRESHOLD,
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
        overlap = seen & set(rows)
        assert not overlap, f"{state.value} overlaps an earlier state on {len(overlap)} rows"
        seen.update(rows)

    assert len(seen) == total, f"expected every one of {total} rows to be classified"
