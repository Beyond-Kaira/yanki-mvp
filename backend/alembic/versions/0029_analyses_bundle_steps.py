"""analyses.bundle_steps JSON for thin bundle orchestrator (mod-8)

Revision ID: 0029_analyses_bundle_steps
Revises: 0028_module_runs
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0029_analyses_bundle_steps"
down_revision: str | None = "0028_module_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "analyses",
        sa.Column(
            "bundle_steps",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("analyses", "bundle_steps")
