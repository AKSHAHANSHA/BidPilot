"""marketplace layer

Adds the TenderSphere marketplace on top of the original BidPilot analysis schema without
touching it:

- `users.account_type` (vendor|company; existing users backfilled as `vendor`)
- `vendor_profiles` — lightweight identity for marketplace vendors
- `market_projects` — public listings a company posts for vendors to browse
- `applications` — a vendor's submission to a project, carrying an AI screening score
- `notifications` — polled in-app events for the notification bell

The existing `tenders` / `analyses` / … schema is untouched; the bid-readiness pipeline
becomes a vendor-only "AI self-check" tool linked from the vendor dashboard.

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-28

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Kept as literal SQL rather than a Python import so the migration can be replayed against a
# past code state — the migration must not depend on today's enum values.
_ACCOUNT_TYPES = "'vendor', 'company'"
_MARKET_PROJECT_STATUSES = "'draft', 'open', 'closed', 'awarded'"
_APPLICATION_STATUSES = (
    "'submitted', 'screening', 'screened', 'shortlisted', 'rejected', 'withdrawn'"
)
_NOTIFICATION_KINDS = (
    "'application_received', 'application_screened', "
    "'application_status_changed', 'project_published'"
)


def upgrade() -> None:
    # --- users.account_type ----------------------------------------------------
    op.add_column(
        "users",
        sa.Column(
            "account_type",
            sa.String(length=16),
            nullable=False,
            server_default="vendor",
        ),
    )
    op.create_check_constraint(
        "ck_users_account_type",
        "users",
        f"account_type IN ({_ACCOUNT_TYPES})",
    )
    # Drop the server default now that existing rows are backfilled — future inserts must be
    # explicit so a bug that omits the column fails loudly instead of silently defaulting.
    op.alter_column("users", "account_type", server_default=None)

    # --- vendor_profiles -------------------------------------------------------
    op.create_table(
        "vendor_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("location", sa.String(length=120), nullable=True),
        sa.Column("primary_category", sa.String(length=80), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("contact_email", sa.String(length=320), nullable=True),
        sa.Column("contact_phone", sa.String(length=40), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_vendor_profiles_owner_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vendor_profiles")),
        sa.UniqueConstraint(
            "owner_user_id", name=op.f("uq_vendor_profiles_owner_user_id")
        ),
    )

    # --- market_projects -------------------------------------------------------
    op.create_table(
        "market_projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("posted_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("company_display_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("location", sa.String(length=120), nullable=True),
        sa.Column("budget_aed", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("submission_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cover_image_url", sa.String(length=1024), nullable=True),
        sa.Column("requirements_summary", sa.Text(), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"status IN ({_MARKET_PROJECT_STATUSES})",
            name=op.f("ck_market_projects_market_project_status"),
        ),
        sa.CheckConstraint(
            "budget_aed IS NULL OR budget_aed >= 0",
            name=op.f("ck_market_projects_market_project_budget_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["posted_by_user_id"],
            ["users.id"],
            name=op.f("fk_market_projects_posted_by_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_market_projects")),
    )
    op.create_index(
        "ix_market_projects_status_deadline",
        "market_projects",
        ["status", "submission_deadline"],
    )
    op.create_index("ix_market_projects_category", "market_projects", ["category"])
    op.create_index("ix_market_projects_posted_by", "market_projects", ["posted_by_user_id"])

    # --- applications ----------------------------------------------------------
    op.create_table(
        "applications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("vendor_user_id", sa.Uuid(), nullable=False),
        sa.Column("document_storage_key", sa.String(length=512), nullable=True),
        sa.Column("document_original_name", sa.String(length=255), nullable=True),
        sa.Column("ai_score", sa.Integer(), nullable=True),
        sa.Column("ai_summary", sa.String(length=2000), nullable=True),
        sa.Column("ai_assessment", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="submitted"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.String(length=2000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"status IN ({_APPLICATION_STATUSES})",
            name=op.f("ck_applications_application_status"),
        ),
        sa.CheckConstraint(
            "ai_score IS NULL OR (ai_score >= 0 AND ai_score <= 100)",
            name=op.f("ck_applications_ai_score_range"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["market_projects.id"],
            name=op.f("fk_applications_project_id_market_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["vendor_user_id"],
            ["users.id"],
            name=op.f("fk_applications_vendor_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_applications")),
        sa.UniqueConstraint(
            "project_id", "vendor_user_id", name=op.f("uq_applications_project_vendor")
        ),
    )
    op.create_index(
        "ix_applications_vendor_status", "applications", ["vendor_user_id", "status"]
    )
    op.create_index(
        "ix_applications_project_status", "applications", ["project_id", "status"]
    )

    # --- notifications ---------------------------------------------------------
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("recipient_user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.String(length=1000), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"kind IN ({_NOTIFICATION_KINDS})",
            name=op.f("ck_notifications_notification_kind"),
        ),
        sa.ForeignKeyConstraint(
            ["recipient_user_id"],
            ["users.id"],
            name=op.f("fk_notifications_recipient_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    op.create_index(
        "ix_notifications_recipient_read", "notifications", ["recipient_user_id", "read_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_recipient_read", table_name="notifications")
    op.drop_table("notifications")

    op.drop_index("ix_applications_project_status", table_name="applications")
    op.drop_index("ix_applications_vendor_status", table_name="applications")
    op.drop_table("applications")

    op.drop_index("ix_market_projects_posted_by", table_name="market_projects")
    op.drop_index("ix_market_projects_category", table_name="market_projects")
    op.drop_index("ix_market_projects_status_deadline", table_name="market_projects")
    op.drop_table("market_projects")

    op.drop_table("vendor_profiles")

    op.drop_constraint("ck_users_account_type", "users", type_="check")
    op.drop_column("users", "account_type")
