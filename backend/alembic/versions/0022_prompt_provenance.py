"""prompt provenance — source + locked flags for guided edits

Revision ID: 0022_prompt_provenance
Revises: 0021_analysis_run_mode
Create Date: 2026-08-19

``source`` records how a prompt entered the set (training lineage).
``locked`` reserves future system-owned prompts the user cannot edit.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "0022_prompt_provenance"
down_revision = "0021_analysis_run_mode"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "prompts",
        sa.Column("source", sa.Text(), nullable=False, server_default="generated"),
    )
    op.add_column(
        "prompts",
        sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("prompts", "locked")
    op.drop_column("prompts", "source")
