"""users.auth_provider / auth_subject, and a password that may be absent

Revision ID: 0019_oauth_identity
Revises: 0018_invitations_audit_integrity
Create Date: 2026-08-17

Additive, plus one constraint relaxation.

`password_hash` becomes nullable because an account created through Google or
Apple has no password to hash. Relaxing a NOT NULL never invalidates an
existing row, so every password account keeps working untouched.

`auth_subject` is the provider's immutable id for the account. Matching on the
email alone would lose the user the day they change it at the provider; the
subject is what survives that. The pair is unique so two users can never claim
the same provider identity, and NULLs are exempt from the constraint in
Postgres, which is what keeps every password account out of its way.

The downgrade re-imposes NOT NULL, so it fails while a passwordless account
exists. That is the honest failure: there is no password to invent for those
rows, and silently deleting the accounts would be worse.
"""

import sqlalchemy as sa

from alembic import op

revision = "0019_oauth_identity"
down_revision = "0018_invitations_audit_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "password_hash", existing_type=sa.Text(), nullable=True)
    op.add_column("users", sa.Column("auth_provider", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("auth_subject", sa.Text(), nullable=True))
    op.create_unique_constraint(
        "uq_users_auth_provider_subject",
        "users",
        ["auth_provider", "auth_subject"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_users_auth_provider_subject", "users", type_="unique")
    op.drop_column("users", "auth_subject")
    op.drop_column("users", "auth_provider")
    op.alter_column("users", "password_hash", existing_type=sa.Text(), nullable=False)
