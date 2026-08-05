"""The append-only guard, proved against a real Postgres.

The audit trail's tamper-resistance rests on two claims, and only one of them
can be checked on SQLite. The row hash is checked in ``test_audit_api.py``,
where SQLite's lack of the trigger is what makes an out-of-band edit possible
to stage at all. This module checks the other claim — that on the database the
product actually runs on, UPDATE and DELETE are refused — which is a statement
about migration 0018 rather than about any Python code, and therefore cannot be
tested anywhere but here.

Skips without ``TEST_DATABASE_URL``, like ``test_migrations.py``, so the default
``uv run pytest`` stays hermetic and offline.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config

from alembic import command
from app.config import get_settings

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL.startswith("postgresql"),
    reason="TEST_DATABASE_URL is not a Postgres URL (set by `make test`)",
)

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _reset(engine: sa.Engine) -> None:
    """An empty database. Dropping the schema takes the trigger's function too.

    ``DROP TABLE`` would leave ``yanki_audit_events_append_only`` behind, and the
    next ``upgrade head`` would then hit a ``CREATE OR REPLACE`` on a function
    the previous run defined — passing for the wrong reason.
    """

    with engine.begin() as connection:
        connection.execute(sa.text("DROP SCHEMA public CASCADE"))
        connection.execute(sa.text("CREATE SCHEMA public"))


@pytest.fixture()
def migrated_engine(monkeypatch):
    """A Postgres database at ``head``, torn down afterwards.

    ``alembic/env.py`` reads its URL from ``get_settings()`` rather than from
    ``alembic.ini``, so the override goes through the environment and the
    settings cache is cleared on both sides — the same dance as
    ``test_migrations.py``.
    """

    engine = sa.create_engine(TEST_DATABASE_URL, future=True)
    try:
        engine.connect().close()
    except Exception as exc:  # pragma: no cover - infra guard
        engine.dispose()
        pytest.skip(f"Postgres unreachable at TEST_DATABASE_URL: {exc}")

    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    get_settings.cache_clear()
    _reset(engine)

    config = Config()
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")

    try:
        yield engine
    finally:
        _reset(engine)
        engine.dispose()
        get_settings.cache_clear()


def _insert_event(connection) -> uuid.UUID:
    event_id = uuid.uuid4()
    connection.execute(
        sa.text(
            "INSERT INTO audit_events (id, occurred_at, actor_type, action, outcome) "
            "VALUES (:id, :at, 'system', 'test:event', 'success')"
        ),
        {"id": event_id, "at": datetime.now(UTC)},
    )
    return event_id


def test_an_audit_event_can_be_inserted(migrated_engine):
    """The guard blocks UPDATE and DELETE — it must not block the writes."""

    with migrated_engine.begin() as connection:
        event_id = _insert_event(connection)

    with migrated_engine.connect() as connection:
        found = connection.execute(
            sa.text("SELECT action FROM audit_events WHERE id = :id"), {"id": event_id}
        ).scalar()
    assert found == "test:event"


def test_updating_an_audit_event_is_refused_by_the_database(migrated_engine):
    with migrated_engine.begin() as connection:
        event_id = _insert_event(connection)

    with pytest.raises(sa.exc.DBAPIError) as exc:
        with migrated_engine.begin() as connection:
            connection.execute(
                sa.text("UPDATE audit_events SET action = 'tampered' WHERE id = :id"),
                {"id": event_id},
            )
    assert "append-only" in str(exc.value)

    # And the row is untouched — the transaction that tried it rolled back.
    with migrated_engine.connect() as connection:
        assert (
            connection.execute(
                sa.text("SELECT action FROM audit_events WHERE id = :id"), {"id": event_id}
            ).scalar()
            == "test:event"
        )


def test_deleting_an_audit_event_is_refused_by_the_database(migrated_engine):
    with migrated_engine.begin() as connection:
        event_id = _insert_event(connection)

    with pytest.raises(sa.exc.DBAPIError) as exc:
        with migrated_engine.begin() as connection:
            connection.execute(sa.text("DELETE FROM audit_events WHERE id = :id"), {"id": event_id})
    assert "append-only" in str(exc.value)

    with migrated_engine.connect() as connection:
        assert (
            connection.execute(
                sa.text("SELECT count(*) FROM audit_events WHERE id = :id"), {"id": event_id}
            ).scalar()
            == 1
        )


def test_a_bulk_delete_is_refused_too(migrated_engine):
    """FOR EACH ROW, so 'DELETE FROM audit_events' with no WHERE also fails."""

    with migrated_engine.begin() as connection:
        _insert_event(connection)
        _insert_event(connection)

    with pytest.raises(sa.exc.DBAPIError):
        with migrated_engine.begin() as connection:
            connection.execute(sa.text("DELETE FROM audit_events"))

    with migrated_engine.connect() as connection:
        assert connection.execute(sa.text("SELECT count(*) FROM audit_events")).scalar() == 2
