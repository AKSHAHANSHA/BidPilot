"""baseline

Phase 0 introduces no tables. This empty revision exists so that `alembic upgrade head`
runs against a fresh database, creates the `alembic_version` bookkeeping table, and gives
Phase 1's first schema revision a parent to hang from.

Revision ID: 0001
Revises:
Create Date: 2026-07-26

"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
