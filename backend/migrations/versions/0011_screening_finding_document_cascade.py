"""screening findings cascade with the document they cite

`screening_findings.matched_document_id` was created `ON DELETE SET NULL`, which contradicts the
`present_needs_document` check constraint on the same table: nulling the column on a `present`
or `present_expired` row makes it violate the check, so Postgres aborted the delete. The
practical effect was that any application whose screening had found a document could not be
deleted, and neither could its vendor.

Cascading resolves it in the direction the product's rules already point — a finding that says
"supplied, see this file" is a claim about that file, and must not outlive it.

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-28

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "fk_screening_findings_matched_document_id_application_documents"


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "screening_findings", type_="foreignkey")
    op.create_foreign_key(
        _CONSTRAINT,
        "screening_findings",
        "application_documents",
        ["matched_document_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "screening_findings", type_="foreignkey")
    op.create_foreign_key(
        _CONSTRAINT,
        "screening_findings",
        "application_documents",
        ["matched_document_id"],
        ["id"],
        ondelete="SET NULL",
    )
