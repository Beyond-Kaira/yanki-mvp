"""analyses.created_by_user_id — attribute GEO runs to the submitting user

Revision ID: 0019_analysis_created_by_user
Revises: 0018_invitations_audit_integrity
Create Date: 2026-08-17

Nullable additive column. Existing rows stay NULL (legacy / anonymous scope).
No FK yet — same deferral as analyses.org_id (ADR-35).
"""

import sqlalchemy as sa

from alembic import op

revision = "0019_analysis_created_by_user"
down_revision = "0018_invitations_audit_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analyses",
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        "ix_analyses_created_by_user_id",
        "analyses",
        ["created_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_analyses_created_by_user_id", table_name="analyses")
    op.drop_column("analyses", "created_by_user_id")
