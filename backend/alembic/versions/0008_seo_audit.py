"""seo audit: nullable analyses columns + seo_checks table (ADR-31)

Additive only, and the same shape as 0007. Three **nullable** columns on
``analyses`` (``seo_score``, ``seo_grade``, ``seo_status``) with no server
defaults — null means "this run did not audit", which is what every existing row
honestly is — plus the ``seo_checks`` table holding one row per check.

``check_id`` is plain text rather than an enum on purpose: the catalogue gains
and loses checks between releases, and a stored row has to stay readable after
its check is retired.

Revision ID: 0008_seo_audit
Revises: 0007_serp_visibility
Create Date: 2026-08-03
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0008_seo_audit"
down_revision = "0007_serp_visibility"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("analyses", sa.Column("seo_score", sa.Float(), nullable=True))
    op.add_column("analyses", sa.Column("seo_grade", sa.Text(), nullable=True))
    op.add_column("analyses", sa.Column("seo_status", sa.Text(), nullable=True))

    op.create_table(
        "seo_checks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "analysis_id",
            sa.Uuid(),
            sa.ForeignKey("analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("check_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # Every read is "the checks for one analysis, in order" — a results page
    # rendering its own evidence.
    op.create_index("ix_seo_checks_analysis_id", "seo_checks", ["analysis_id"])
    # The cross-sectional question this table exists to make answerable: how many
    # audited sites fail a given check.
    op.create_index("ix_seo_checks_check_id_status", "seo_checks", ["check_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_seo_checks_check_id_status", table_name="seo_checks")
    op.drop_index("ix_seo_checks_analysis_id", table_name="seo_checks")
    op.drop_table("seo_checks")
    op.drop_column("analyses", "seo_status")
    op.drop_column("analyses", "seo_grade")
    op.drop_column("analyses", "seo_score")
