"""user-owned SEO projects and independent Site Audit jobs

Revision ID: 0009_site_audit_projects
Revises: 0008_seo_audit
Create Date: 2026-08-03
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0009_site_audit_projects"
down_revision = "0008_seo_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "seo_projects",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column("domain_key", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "user_id",
            "domain_key",
            name="uq_seo_projects_user_domain_key",
        ),
    )
    op.create_index("ix_seo_projects_user_id", "seo_projects", ["user_id"])

    op.create_table(
        "site_audits",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("seo_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_step", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("page_limit", sa.Integer(), nullable=False, server_default="10"),
        sa.Column(
            "profile_id",
            sa.Text(),
            nullable=False,
            server_default="site_audit_mobile",
        ),
        sa.Column("js_rendering", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("pages_discovered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pages_crawled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_errors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_warnings", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_notices", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("health_score", sa.Integer(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("page_limit BETWEEN 1 AND 500", name="ck_site_audits_page_limit"),
        sa.CheckConstraint("progress BETWEEN 0 AND 100", name="ck_site_audits_progress"),
        sa.CheckConstraint(
            "health_score IS NULL OR health_score BETWEEN 0 AND 100",
            name="ck_site_audits_health_score",
        ),
    )
    op.create_index("ix_site_audits_project_id", "site_audits", ["project_id"])
    op.create_index(
        "ix_site_audits_project_created_at",
        "site_audits",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_site_audits_queue",
        "site_audits",
        ["status", "claimed_at", "created_at"],
    )
    op.create_index(
        "uq_site_audits_one_active_per_project",
        "site_audits",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )

    op.create_table(
        "site_audit_pages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "audit_id",
            sa.Uuid(),
            sa.ForeignKey("site_audits.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("requested_url", sa.Text(), nullable=False),
        sa.Column("final_url", sa.Text(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("h1_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("meta_description", sa.Text(), nullable=True),
        sa.Column("html_lang", sa.Text(), nullable=True),
        sa.Column(
            "issues",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "schemas",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "audit_id",
            "final_url",
            name="uq_site_audit_pages_audit_final_url",
        ),
    )
    op.create_index("ix_site_audit_pages_audit_id", "site_audit_pages", ["audit_id"])


def downgrade() -> None:
    op.drop_index("ix_site_audit_pages_audit_id", table_name="site_audit_pages")
    op.drop_table("site_audit_pages")
    op.drop_index(
        "uq_site_audits_one_active_per_project",
        table_name="site_audits",
    )
    op.drop_index("ix_site_audits_queue", table_name="site_audits")
    op.drop_index("ix_site_audits_project_created_at", table_name="site_audits")
    op.drop_index("ix_site_audits_project_id", table_name="site_audits")
    op.drop_table("site_audits")
    op.drop_index("ix_seo_projects_user_id", table_name="seo_projects")
    op.drop_table("seo_projects")
