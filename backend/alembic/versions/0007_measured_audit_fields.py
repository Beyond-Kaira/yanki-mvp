"""measured audit fields (composite GEO)

Additive only: new nullable columns on analyses + responses so measured audit
records, reliability, and interventions can persist without breaking legacy
rows. geo_score stays a Float; its semantic becomes 0-100 composite (app-level).

Revision ID: 0007_measured_audit_fields
Revises: 0006_auth_sessions
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0007_measured_audit_fields"
down_revision = "0006_auth_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analyses",
        sa.Column("reliability_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "analyses",
        sa.Column(
            "interventions",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
    )
    op.add_column(
        "responses",
        sa.Column(
            "audit",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("responses", "audit")
    op.drop_column("analyses", "interventions")
    op.drop_column("analyses", "reliability_score")
