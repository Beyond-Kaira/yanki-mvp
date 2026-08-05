"""The last-owner guard under concurrency, proved against a real Postgres.

Every lockout guard in ``admin_routes`` is a check-then-act: count the active
owners, then demote / disable / remove one. Read on one connection that reads
correctly, and it is obviously right. Run it twice at once and it is obviously
wrong — two administrators demoting the two remaining owners at the same moment
each read a count of 2, each pass the guard, and the organization is left with
no owner at all. Two browser tabs are enough; it needs no malice and no load.

``_owner_count`` therefore selects the owner memberships ``FOR UPDATE`` rather
than counting them with an aggregate. This module is the only place that
property can be checked, because SQLite runs one connection and the dialect
silently omits ``FOR UPDATE`` — so the unit suite cannot fail if the lock is
deleted, and every one of its assertions would still pass.

Skips without ``TEST_DATABASE_URL``, like the other Postgres-gated modules.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from app.api.admin_routes import _owner_count
from app.db.base import Base
from app.db.models import Membership, Organization, User

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL.startswith("postgresql"),
    reason="TEST_DATABASE_URL is not a Postgres URL (set by `make test`)",
)


@pytest.fixture()
def engine():
    engine = sa.create_engine(TEST_DATABASE_URL, future=True)
    try:
        engine.connect().close()
    except Exception as exc:  # pragma: no cover - infra guard
        engine.dispose()
        pytest.skip(f"Postgres unreachable at TEST_DATABASE_URL: {exc}")

    # The schema comes from the models rather than the migration chain: this
    # module is about row locking, not about DDL, and create_all is far faster.
    with engine.begin() as connection:
        connection.execute(sa.text("DROP SCHEMA public CASCADE"))
        connection.execute(sa.text("CREATE SCHEMA public"))
    Base.metadata.create_all(engine)

    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(sa.text("DROP SCHEMA public CASCADE"))
            connection.execute(sa.text("CREATE SCHEMA public"))
        engine.dispose()


@pytest.fixture()
def two_owners(engine):
    """An organization with exactly two active owners, and its id."""

    factory = sessionmaker(bind=engine, future=True, class_=Session)
    with factory() as session:
        org = Organization(
            name="Acme", slug=f"acme-{uuid.uuid4().hex[:8]}", kind="company", status="active"
        )
        session.add(org)
        session.flush()

        owner_ids = []
        for index in range(2):
            user = User(
                email=f"owner{index}-{uuid.uuid4().hex[:8]}@acme.test",
                password_hash="x",
                status="active",
                created_at=datetime.now(UTC),
            )
            session.add(user)
            session.flush()
            session.add(Membership(org_id=org.id, user_id=user.id, role="owner", status="active"))
            owner_ids.append(user.id)
        session.commit()
        return org.id, owner_ids


def test_counting_owners_takes_a_row_lock(engine, two_owners):
    """A second transaction cannot read the owner set while the first holds it.

    Proved by giving the second connection a 1-second ``lock_timeout``: if
    ``_owner_count`` does not lock, it returns immediately and this test fails
    on the missing exception rather than on a hang.
    """

    org_id, _ = two_owners
    factory = sessionmaker(bind=engine, future=True, class_=Session)

    first = factory()
    second = factory()
    try:
        assert _owner_count(first, org_id) == 2  # takes the lock, holds it

        second.execute(sa.text("SET LOCAL lock_timeout = '1s'"))
        with pytest.raises(sa.exc.OperationalError) as exc:
            _owner_count(second, org_id)
        assert "lock timeout" in str(exc.value).lower()
    finally:
        second.rollback()
        first.rollback()
        second.close()
        first.close()


def test_two_concurrent_demotions_cannot_strip_the_last_owner(engine, two_owners):
    """The race that motivates the lock, run for real.

    Transaction A demotes one owner. Transaction B — which read a count of two
    before A committed — must block, re-read, and see one. Without the lock both
    would commit and the organization would have zero owners, which is the
    unrecoverable state.
    """

    org_id, owner_ids = two_owners
    factory = sessionmaker(bind=engine, future=True, class_=Session)

    first = factory()
    second = factory()
    try:
        # A: passes the guard and demotes the first owner.
        assert _owner_count(first, org_id) == 2
        first.execute(
            sa.update(Membership)
            .where(Membership.org_id == org_id, Membership.user_id == owner_ids[0])
            .values(role="admin")
        )
        first.commit()

        # B: now re-reads under the (released) lock and sees the truth.
        assert _owner_count(second, org_id) == 1

        remaining = second.scalar(
            sa.select(sa.func.count())
            .select_from(Membership)
            .where(
                Membership.org_id == org_id,
                Membership.role == "owner",
                Membership.status == "active",
            )
        )
        assert remaining == 1
    finally:
        second.rollback()
        first.rollback()
        second.close()
        first.close()


def test_a_disabled_owner_does_not_count_as_an_owner(engine, two_owners):
    """The count is of owners who can actually act, not of rows saying 'owner'.

    A disabled account holding the owner role cannot log in, so an organization
    whose only owner is disabled is already locked out. Counting them would let
    the guard wave through the change that strands it.
    """

    org_id, owner_ids = two_owners
    factory = sessionmaker(bind=engine, future=True, class_=Session)

    with factory() as session:
        session.execute(sa.update(User).where(User.id == owner_ids[0]).values(status="disabled"))
        session.commit()

    with factory() as session:
        assert _owner_count(session, org_id) == 1
