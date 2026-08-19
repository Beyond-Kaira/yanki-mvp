"""analyses.run_mode — quick vs guided profile pause

Revision ID: 0021_analysis_run_mode
Revises: 0020_oauth_identity
Create Date: 2026-08-19

Additive column. Existing rows default to ``quick`` (current behaviour).
Guided runs pause after prompts with ``status='awaiting_review'`` (ADR-50).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "0021_analysis_run_mode"
down_revision = "0020_oauth_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "analyses",
        sa.Column(
            "run_mode",
            sa.Text(),
            nullable=False,
            server_default="quick",
        ),
    )


def downgrade() -> None:
    op.drop_column("analyses", "run_mode")
