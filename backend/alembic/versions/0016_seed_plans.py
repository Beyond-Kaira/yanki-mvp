"""seed the plan catalog (Phase 7 / P7.6 follow-up)

Revision ID: 0016_seed_plans
Revises: 0015_billing
Create Date: 2026-08-05

0015 created the `plans` table and left it empty, and `seed_plans()` was written
but never called from anything that runs at deploy time. Verifying production
after the merge is what surfaced it: `plans` had zero rows.

That is not currently visible — nothing on a live path consults a quota yet
(backlinks, the only caller, ship dark) — but it is a trap laid for whoever
wires the first one. `limit_for()` deliberately falls back to Free rather than
to unlimited, and with no Free row to fall back TO it returns 0, which reads as
"you may do none of this". Fail-closed is the right direction and a total
refusal is still an outage; the fix is to make sure the catalog is never empty.

Seeded here rather than at application startup because a migration runs exactly
once per database, in the migrate-before-serve step, with no race between
several booting containers all trying to insert the same rows.

Idempotent: each row is inserted only if its key is absent, so a re-run or a
database that already has a catalog converges instead of colliding.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import sqlalchemy as sa

from alembic import op

revision = "0016_seed_plans"
down_revision = "0015_billing"
branch_labels = None
depends_on = None

# Mirrors app.services.billing.DEFAULT_PLANS. Duplicated on purpose: a migration
# must keep describing the catalog as it was when written, so importing the
# living constant would let a later pricing change rewrite history.
_PLANS = (
    (
        "free",
        "Free",
        Decimal("0"),
        {
            "analyses": 5,
            "site_audits": 1,
            "backlink_refreshes": 0,
            "projects": 1,
            "monthly_credit_usd": "0",
        },
    ),
    (
        "starter",
        "Starter",
        Decimal("49"),
        {
            "analyses": 100,
            "site_audits": 20,
            "backlink_refreshes": 4,
            "projects": 3,
            "monthly_credit_usd": "10",
        },
    ),
    (
        "pro",
        "Pro",
        Decimal("149"),
        {
            "analyses": 500,
            "site_audits": 100,
            "backlink_refreshes": 30,
            "projects": 10,
            "monthly_credit_usd": "50",
        },
    ),
    (
        "business",
        "Business",
        Decimal("399"),
        {
            "analyses": 2000,
            "site_audits": 500,
            "backlink_refreshes": 120,
            "projects": 50,
            "monthly_credit_usd": "200",
        },
    ),
    (
        "enterprise",
        "Enterprise",
        Decimal("0"),
        {
            "analyses": None,
            "site_audits": None,
            "backlink_refreshes": None,
            "projects": None,
            "monthly_credit_usd": None,
        },
    ),
)

_meta = sa.MetaData()
_plans = sa.Table(
    "plans",
    _meta,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column("key", sa.Text),
    sa.Column("name", sa.Text),
    sa.Column("limits", sa.JSON),
    sa.Column("monthly_price_usd", sa.Numeric(10, 2)),
    sa.Column("active", sa.Boolean),
    # Supplied explicitly below: the model defaults this in PYTHON, so a Core
    # insert leaves it NULL and the NOT NULL constraint rejects the row. The
    # same asymmetry bit the org backfill in 0012.
    sa.Column("created_at", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    connection = op.get_bind()
    existing = {row[0] for row in connection.execute(sa.select(_plans.c.key))}
    for key, name, price, limits in _PLANS:
        if key in existing:
            continue
        connection.execute(
            sa.insert(_plans).values(
                id=uuid.uuid4(),
                key=key,
                name=name,
                limits=limits,
                monthly_price_usd=price,
                active=True,
                created_at=datetime.now(UTC),
            )
        )


def downgrade() -> None:
    """Remove only the rows this migration seeded, by key.

    A blanket DELETE would take any plan an operator added by hand with it.
    """

    connection = op.get_bind()
    connection.execute(sa.delete(_plans).where(_plans.c.key.in_([key for key, *_ in _PLANS])))
