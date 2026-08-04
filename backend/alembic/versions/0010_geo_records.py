"""geo_records table + analyses.citation_summary

Columnar copy of each Kaira-style measured/simulated audit record (one row per
prompt), plus an analysis-level citation aggregate for GET /analyses.

Revision ID: 0010_geo_records
Revises: 0009_measured_audit_fields
Create Date: 2026-08-03
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0010_geo_records"
down_revision = "0009_measured_audit_fields"
branch_labels = None
depends_on = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column(
        "analyses",
        sa.Column("citation_summary", _JSON, nullable=True),
    )
    op.create_table(
        "geo_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "analysis_id",
            sa.Uuid(),
            sa.ForeignKey("analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "response_id",
            sa.Uuid(),
            sa.ForeignKey("responses.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("brand", sa.Text(), nullable=False),
        sa.Column("sector", sa.Text(), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("prompt_group", sa.Text(), nullable=True),
        sa.Column("intent", sa.Text(), nullable=True),
        sa.Column("measurement_mode", sa.Text(), nullable=True),
        sa.Column("search_provider", sa.Text(), nullable=True),
        sa.Column("search_results", _JSON, nullable=True),
        sa.Column("search_visibility", _JSON, nullable=True),
        sa.Column("grounded_answer", sa.Text(), nullable=True),
        sa.Column("simulated_answer", sa.Text(), nullable=True),
        sa.Column("mentioned", sa.Boolean(), nullable=True),
        sa.Column("rank_position", sa.Integer(), nullable=True),
        sa.Column("mention_context", sa.Text(), nullable=True),
        sa.Column("competitors", _JSON, nullable=True),
        sa.Column("answer_summary", sa.Text(), nullable=True),
        sa.Column("recommendation_reasoning", sa.Text(), nullable=True),
        sa.Column("reasoning_trace", _JSON, nullable=True),
        sa.Column("citations", _JSON, nullable=True),
        sa.Column("citation_metrics", _JSON, nullable=True),
        sa.Column("visibility_drivers", _JSON, nullable=True),
        sa.Column("visibility_gaps", _JSON, nullable=True),
        sa.Column("trust_signals", _JSON, nullable=True),
        sa.Column("entities_associated_with_brand", _JSON, nullable=True),
        sa.Column("sentiment", sa.Text(), nullable=True),
        sa.Column("content_improvement_opportunities", _JSON, nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Boolean(), nullable=True),
        sa.Column("schema_version", sa.Text(), nullable=True),
        sa.Column("owned_domains", _JSON, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_geo_records_analysis_id", "geo_records", ["analysis_id"])


def downgrade() -> None:
    op.drop_index("ix_geo_records_analysis_id", table_name="geo_records")
    op.drop_table("geo_records")
    op.drop_column("analyses", "citation_summary")
