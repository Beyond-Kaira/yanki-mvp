"""invitations + audit-event tamper evidence (Phase 7 / P7.4)

Revision ID: 0018_invitations_audit_integrity
Revises: 0017_user_status
Create Date: 2026-08-05

Two additive changes and one guard.

**`invitations`** is a new table. Nothing reads it before this migration, so
there is no backfill and no ordering hazard.

**`audit_events.record_hash`** is a new nullable column. Nullable is the point:
rows written before it existed cannot be given a credible hash afterwards, and
back-filling one would manufacture evidence rather than record it. The verifier
reports those rows as unverifiable.

**The guard** is a pair of Postgres triggers that raise on UPDATE, DELETE or
TRUNCATE of `audit_events`. The application never issues any of them — but "the
application never does that" is a claim about code, and an audit trail should
rest on a claim about the database.

Two triggers rather than one because a row-level trigger does not fire on
TRUNCATE: Postgres swaps the file rather than iterating rows, so a single
`TRUNCATE audit_events` would otherwise have erased the whole trail using
nothing but the application's own role. TRUNCATE triggers must be
`FOR EACH STATEMENT`.

Postgres only: SQLite unit tests create their schema from the models with
`create_all`, so they never see either trigger, and nothing in the test suite
mutates an audit row.
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0018_invitations_audit_integrity"
down_revision = "0017_user_status"
branch_labels = None
depends_on = None


# RESTRICT on the trigger is deliberate over a rule or a revoked GRANT: it fires
# for every role including the owner the app connects as, and it names itself in
# the error, so the failure explains the policy instead of looking like a bug.
_GUARD_FUNCTION = """
CREATE OR REPLACE FUNCTION yanki_audit_events_append_only()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        'audit_events is append-only: % is not permitted', TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;
"""

_GUARD_TRIGGER = """
CREATE TRIGGER audit_events_append_only
BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION yanki_audit_events_append_only();
"""

# TRUNCATE needs its OWN trigger, and forgetting it is the whole game.
#
# A row-level trigger does not fire on TRUNCATE — Postgres does not iterate the
# rows, it swaps the file — so `TRUNCATE audit_events` would have sailed
# straight past the guard above and erased the entire trail using nothing but
# the application's own database role. That is a far more plausible act than the
# per-row DELETE the first trigger blocks: it is one word, it is what somebody
# reaches for to "clear the log", and it leaves nothing behind to notice.
#
# TRUNCATE triggers must be FOR EACH STATEMENT; there are no rows to be "each"
# of. Found by an adversarial verification pass, not by writing the first one.
_TRUNCATE_GUARD = """
CREATE TRIGGER audit_events_no_truncate
BEFORE TRUNCATE ON audit_events
FOR EACH STATEMENT EXECUTE FUNCTION yanki_audit_events_append_only();
"""


def upgrade() -> None:
    op.create_table(
        "invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("invited_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_user_id", sa.Uuid(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["accepted_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_invitations_token_hash"),
    )
    op.create_index("ix_invitations_email", "invitations", ["email"], unique=False)
    op.create_index("ix_invitations_org_status", "invitations", ["org_id", "status"], unique=False)
    op.create_index(
        "uq_invitations_pending_org_email",
        "invitations",
        ["org_id", "email"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
        sqlite_where=sa.text("status = 'pending'"),
    )

    op.add_column("audit_events", sa.Column("record_hash", sa.Text(), nullable=True))

    if op.get_bind().dialect.name == "postgresql":
        op.execute(_GUARD_FUNCTION)
        op.execute(_GUARD_TRIGGER)
        op.execute(_TRUNCATE_GUARD)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS audit_events_no_truncate ON audit_events")
        op.execute("DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events")
        op.execute("DROP FUNCTION IF EXISTS yanki_audit_events_append_only()")

    op.drop_column("audit_events", "record_hash")

    op.drop_index("uq_invitations_pending_org_email", table_name="invitations")
    op.drop_index("ix_invitations_org_status", table_name="invitations")
    op.drop_index("ix_invitations_email", table_name="invitations")
    op.drop_table("invitations")
