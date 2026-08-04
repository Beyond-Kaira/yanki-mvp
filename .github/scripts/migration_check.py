"""Prove the newest migration reverts cleanly, whatever it happens to be.

Used by the `migration` job around ``alembic downgrade -1`` / ``upgrade head``.

This replaces a check that named SERP's tables and columns explicitly. That
version passed for exactly one migration and then failed on the next one for the
wrong reason: after `0008` landed, ``downgrade -1`` correctly removed the SEO
schema and the check complained that SERP was still there. A gate that has to be
rewritten every time it is exercised is a gate people learn to edit rather than
read.

So it asserts a property instead of a list: **the schema round-trips**. Snapshot
at head, step back one revision, come forward again, and the schema must be
byte-identical to where it started. That catches a downgrade that drops the wrong
thing, forgets an index, or leaves a column behind — for any migration, without
naming one. The middle step separately asserts that the downgrade actually *did*
something, so a no-op downgrade cannot pass by doing nothing.

    uv run python ../.github/scripts/migration_check.py snapshot before.json
    uv run alembic downgrade -1
    uv run python ../.github/scripts/migration_check.py changed before.json
    uv run alembic upgrade head
    uv run python ../.github/scripts/migration_check.py compare before.json
"""

from __future__ import annotations

import json
import os
import sys

import sqlalchemy as sa


def _snapshot(url: str) -> dict:
    """Every table, its columns (with type and nullability), and its indexes."""
    engine = sa.create_engine(url)
    try:
        inspector = sa.inspect(engine)
        schema: dict = {}
        for table in sorted(inspector.get_table_names()):
            schema[table] = {
                "columns": sorted(
                    f"{c['name']}:{c['type']!s}:{'null' if c['nullable'] else 'notnull'}"
                    for c in inspector.get_columns(table)
                ),
                "indexes": sorted(
                    f"{i['name']}:{','.join(i['column_names'] or [])}"
                    for i in inspector.get_indexes(table)
                ),
            }
        return schema
    finally:
        engine.dispose()


def _describe(before: dict, after: dict) -> list[str]:
    problems: list[str] = []
    for table in sorted(set(before) | set(after)):
        if table not in after:
            problems.append(f"table {table} disappeared")
            continue
        if table not in before:
            problems.append(f"table {table} appeared")
            continue
        for key in ("columns", "indexes"):
            gone = set(before[table][key]) - set(after[table][key])
            extra = set(after[table][key]) - set(before[table][key])
            problems += [f"{table}.{key}: lost {item}" for item in sorted(gone)]
            problems += [f"{table}.{key}: gained {item}" for item in sorted(extra)]
    return problems


def main(command: str, path: str) -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2

    if command == "snapshot":
        with open(path, "w") as handle:
            json.dump(_snapshot(url), handle, indent=2, sort_keys=True)
        print(f"ok: snapshotted {len(_snapshot(url))} tables at head")
        return 0

    with open(path) as handle:
        before = json.load(handle)
    after = _snapshot(url)
    problems = _describe(before, after)

    if command == "changed":
        # A downgrade that changed nothing is a downgrade that did not run.
        if not problems:
            print(
                "FAIL: `alembic downgrade -1` left the schema identical — the newest "
                "migration's downgrade() does not undo its upgrade().",
                file=sys.stderr,
            )
            return 1
        print(f"ok: the downgrade changed {len(problems)} schema object(s), as it should")
        return 0

    if command == "compare":
        if problems:
            print("FAIL: the schema did not round-trip:", file=sys.stderr)
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            return 1
        print("ok: schema round-tripped exactly through downgrade and upgrade")
        return 0

    print(f"unknown command {command!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("snapshot", "changed", "compare"):
        print(f"usage: {sys.argv[0]} [snapshot|changed|compare] <file>", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
