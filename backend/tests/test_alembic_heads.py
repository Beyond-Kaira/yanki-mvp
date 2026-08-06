"""The migration chain has exactly one head, checked without a database.

``test_migrations.py`` owns everything that needs a live Postgres and skips
without one. This does not: a second head is a pure property of the files on
disk, it is what two branches adding a migration in the same week produce, and
it turns ``alembic upgrade head`` into an error on the deploy that finds it —
which on this repo is production. Keeping the check hermetic means it runs on
every machine and every CI job, including the ones with no Postgres.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _scripts() -> ScriptDirectory:
    config = Config()
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return ScriptDirectory.from_config(config)


def test_there_is_exactly_one_head():
    heads = _scripts().get_heads()

    assert len(heads) == 1, f"expected a single alembic head, found {sorted(heads)}"


def test_every_revision_is_reachable_from_the_head():
    """No orphan file: a migration nothing points at never runs."""

    scripts = _scripts()
    (head,) = scripts.get_heads()

    reachable = {revision.revision for revision in scripts.iterate_revisions(head, "base")}
    on_disk = {revision.revision for revision in scripts.walk_revisions()}

    assert on_disk == reachable
