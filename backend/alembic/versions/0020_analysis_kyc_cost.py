"""Persist KYC provider spend as part of an analysis.

Revision ID: 0020_analysis_kyc_cost
Revises: 0019_analysis_created_by_user
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0020_analysis_kyc_cost"
down_revision: str | None = "0019_analysis_created_by_user"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "analyses",
        sa.Column(
            "kyc_cost_usd",
            sa.Numeric(precision=10, scale=6),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "analyses",
        sa.Column("kyc_usage", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("analyses", "kyc_usage")
    op.drop_column("analyses", "kyc_cost_usd")
