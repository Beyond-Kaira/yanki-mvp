"""users table for email/password authentication.

Revision ID: 0005_users
Revises: 0004_waitlist_signups
Create Date: 2026-07-28
"""

import sqlalchemy as sa

from alembic import op

revision = "0005_users"
down_revision = "0004_waitlist_signups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("users")
