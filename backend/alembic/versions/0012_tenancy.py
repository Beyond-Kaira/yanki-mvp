"""tenancy: organizations, workspaces, memberships, projects + personal-org backfill (P7.1)

Revision ID: 0012_tenancy
Revises: 0011_geo_records
Create Date: 2026-08-05

The riskiest migration in the Admin Platform milestone, done first because the
surface is still small: production held **3 users, 0 seo_projects, 0 site_audits
and 47 analyses** when this was written, and every one of those analyses is
anonymous. The same migration a year from now runs against a database that would
make it frightening.

Four properties it holds:

1. **Additive only.** New tables, new nullable columns. Nothing dropped, renamed
   or narrowed — so the *previous* release keeps running against this schema,
   which is what makes ADR-30's migrate-before-serve rollback real rather than
   theoretical.
2. **No NOT NULL on a populated table.** That rewrites the table under ACCESS
   EXCLUSIVE; on a box shared with four other production tenants it is not a
   trade worth making for a constraint the service layer already enforces.
3. **The hot table is touched last, and barely.** ``analyses`` gets one bare
   nullable column — no FK, no index, so no validation scan and no btree build —
   and it goes last so its lock is held only until commit. ``lock_timeout``
   makes a queued lock fail fast instead of stalling the co-tenants.
4. **The backfill is somewhere it can be tested.** It lives in
   ``app.db.org_backfill`` and runs against SQLite in the suite with adversarial
   fixtures; this file just calls it. A backfill that can only be exercised by
   running Alembic against Postgres is a backfill that gets exercised once.

Anonymous rows keep ``org_id IS NULL``. NULL *is* the public scope — see ADR-35.
Inventing a system org to stamp onto them would mass-write the hot table for no
functional gain and make public rows look owned, which is the one outcome tenant
isolation must never produce.
"""

import sqlalchemy as sa

from alembic import op
from app.db.org_backfill import backfill_orgs

revision = "0012_tenancy"
down_revision = "0011_geo_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Fail fast rather than queue behind someone else's long transaction and
    # stall a box that also serves four other production sites.
    op.execute("SET LOCAL lock_timeout = '3s'")

    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False, server_default="personal"),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("region", sa.Text(), nullable=True),
        sa.Column(
            "owner_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
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
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )
    # Exactly one personal org per user, enforced where it cannot be forgotten.
    op.create_index(
        "uq_organizations_personal_owner",
        "organizations",
        ["owner_user_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'personal'"),
    )
    op.create_index("ix_organizations_status", "organizations", ["status"])

    op.create_table(
        "workspaces",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "org_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
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
        sa.UniqueConstraint("org_id", "slug", name="uq_workspaces_org_slug"),
    )
    op.create_index("ix_workspaces_org_id", "workspaces", ["org_id"])
    op.create_index(
        "uq_workspaces_one_default_per_org",
        "workspaces",
        ["org_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )

    op.create_table(
        "memberships",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "org_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
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
        sa.UniqueConstraint("org_id", "user_id", name="uq_memberships_org_user"),
    )
    op.create_index("ix_memberships_org_id", "memberships", ["org_id"])
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])

    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "org_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column("domain_key", sa.Text(), nullable=False),
        sa.Column("locale", sa.Text(), nullable=False, server_default="en"),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
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
        sa.UniqueConstraint("org_id", "domain_key", name="uq_projects_org_domain_key"),
    )
    op.create_index("ix_projects_org_id", "projects", ["org_id"])
    op.create_index("ix_projects_workspace_id", "projects", ["workspace_id"])

    # seo_projects: small, low-traffic — safe to index and constrain here.
    op.add_column("seo_projects", sa.Column("org_id", sa.Uuid(), nullable=True))
    op.add_column("seo_projects", sa.Column("workspace_id", sa.Uuid(), nullable=True))
    op.add_column("seo_projects", sa.Column("project_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_seo_projects_org_id",
        "seo_projects",
        "organizations",
        ["org_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_seo_projects_workspace_id",
        "seo_projects",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_seo_projects_project_id",
        "seo_projects",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_seo_projects_org_id", "seo_projects", ["org_id"])

    # The hot table, last and lightest: one bare nullable column. No FK (its
    # delete rule would have to be RESTRICT, and there is nothing to restrict
    # yet), no index (every value is NULL). See ADR-35.
    op.add_column("analyses", sa.Column("org_id", sa.Uuid(), nullable=True))

    backfill_orgs(op.get_bind())


def downgrade() -> None:
    """Reverse cleanly. Tenancy rows are lost; nothing else is.

    What a downgrade destroys is exactly what the upgrade invented — orgs,
    workspaces, memberships, projects, and the pointers to them. No analysis,
    response, audit, or user row is touched. That is the property that makes
    rolling this back a real option rather than a paragraph in a runbook.
    """

    op.drop_column("analyses", "org_id")

    op.drop_index("ix_seo_projects_org_id", table_name="seo_projects")
    op.drop_constraint("fk_seo_projects_project_id", "seo_projects", type_="foreignkey")
    op.drop_constraint("fk_seo_projects_workspace_id", "seo_projects", type_="foreignkey")
    op.drop_constraint("fk_seo_projects_org_id", "seo_projects", type_="foreignkey")
    op.drop_column("seo_projects", "project_id")
    op.drop_column("seo_projects", "workspace_id")
    op.drop_column("seo_projects", "org_id")

    op.drop_index("ix_projects_workspace_id", table_name="projects")
    op.drop_index("ix_projects_org_id", table_name="projects")
    op.drop_table("projects")

    op.drop_index("ix_memberships_user_id", table_name="memberships")
    op.drop_index("ix_memberships_org_id", table_name="memberships")
    op.drop_table("memberships")

    op.drop_index("uq_workspaces_one_default_per_org", table_name="workspaces")
    op.drop_index("ix_workspaces_org_id", table_name="workspaces")
    op.drop_table("workspaces")

    op.drop_index("ix_organizations_status", table_name="organizations")
    op.drop_index("uq_organizations_personal_owner", table_name="organizations")
    op.drop_table("organizations")
