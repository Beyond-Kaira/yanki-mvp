"""serp visibility: nullable analyses columns + serp_checks table (ADR-28)

Additive only. Part (a) adds five **nullable** columns to ``analyses``
(``serp_score``, ``serp_hit_count``, ``serp_query_count``, ``serp_status``,
``serp_source``) with no server defaults — deliberately, because null here is
load-bearing: it means "this run did not measure SERP visibility", which is what
every pre-existing row and every run with the feature switched off honestly is.
Backfilling them to 0 would claim we looked and found nothing.

Part (b) creates the ``serp_checks`` table — one row per search query run for an
analysis, holding the evidence behind the number (the query, the matched result,
its rank, and which engines refused to answer). No existing column or constraint
is touched, so this stays under the additive ``alembic/**`` review bar.

Revision ID: 0007_serp_visibility
Revises: 0006_auth_sessions
Create Date: 2026-08-03
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0007_serp_visibility"
down_revision = "0006_auth_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # (a) Nullable summary columns on analyses.
    op.add_column("analyses", sa.Column("serp_score", sa.Float(), nullable=True))
    op.add_column("analyses", sa.Column("serp_hit_count", sa.Integer(), nullable=True))
    op.add_column("analyses", sa.Column("serp_query_count", sa.Integer(), nullable=True))
    op.add_column("analyses", sa.Column("serp_status", sa.Text(), nullable=True))
    op.add_column("analyses", sa.Column("serp_source", sa.Text(), nullable=True))

    # (b) One row per query. ``hit`` is nullable on purpose: NULL is a page we
    # could not read (every engine refused, or the instance was unreachable) and
    # is excluded from the score, while FALSE is a real, counted miss.
    op.create_table(
        "serp_checks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "analysis_id",
            sa.Uuid(),
            sa.ForeignKey("analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("hit", sa.Boolean(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("matched_url", sa.Text(), nullable=True),
        sa.Column("matched_snippet", sa.Text(), nullable=True),
        sa.Column("matched_via", sa.Text(), nullable=True),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unresponsive_engines", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # Every read of this table is "the checks for one analysis, in order" — the
    # results page rendering its own evidence.
    op.create_index(
        "ix_serp_checks_analysis_id",
        "serp_checks",
        ["analysis_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_serp_checks_analysis_id", table_name="serp_checks")
    op.drop_table("serp_checks")
    op.drop_column("analyses", "serp_source")
    op.drop_column("analyses", "serp_status")
    op.drop_column("analyses", "serp_query_count")
    op.drop_column("analyses", "serp_hit_count")
    op.drop_column("analyses", "serp_score")
