"""auth sessions for refresh-token rotation.

Revision ID: 0006_auth_sessions
Revises: 0005_users
Create Date: 2026-07-29
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_auth_sessions"
down_revision = "0005_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("refresh_jti_hash", sa.Text(), nullable=False),
        sa.Column("replaced_by_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "consumed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by_id"],
            ["auth_sessions.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "refresh_jti_hash",
            name="uq_auth_sessions_refresh_jti_hash",
        ),
    )

    op.create_index(
        "ix_auth_sessions_user_id",
        "auth_sessions",
        ["user_id"],
    )
    op.create_index(
        "ix_auth_sessions_family_id",
        "auth_sessions",
        ["family_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_auth_sessions_family_id",
        table_name="auth_sessions",
    )
    op.drop_index(
        "ix_auth_sessions_user_id",
        table_name="auth_sessions",
    )
    op.drop_table("auth_sessions")
