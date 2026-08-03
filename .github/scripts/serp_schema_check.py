"""Assert the SERP schema is present (or absent) in the migrated database.

Used by the `migration` job in serp.yml around `alembic upgrade` /
`alembic downgrade`. It reads the live database rather than the models, because
the thing under test is what the migration *did* — comparing the models to
themselves would pass with no migration at all.

Run from ``backend/`` so the app's dependencies are importable::

    uv run python ../.github/scripts/serp_schema_check.py present
    uv run python ../.github/scripts/serp_schema_check.py absent
"""

from __future__ import annotations

import os
import sys

import sqlalchemy as sa

TABLE = "serp_checks"
ANALYSES_COLUMNS = (
    "serp_score",
    "serp_hit_count",
    "serp_query_count",
    "serp_status",
    "serp_source",
)
# Every column 0007 creates on serp_checks, so a partial CREATE TABLE is caught
# rather than passing on the table name alone.
CHECK_COLUMNS = (
    "id",
    "analysis_id",
    "query",
    "source",
    "hit",
    "rank",
    "matched_url",
    "matched_snippet",
    "matched_via",
    "result_count",
    "unresponsive_engines",
    "created_at",
)


def main(expected: str) -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2

    engine = sa.create_engine(url)
    try:
        inspector = sa.inspect(engine)
        tables = set(inspector.get_table_names())
        analyses = {column["name"] for column in inspector.get_columns("analyses")}
        checks = (
            {column["name"] for column in inspector.get_columns(TABLE)}
            if TABLE in tables
            else set()
        )
    finally:
        engine.dispose()

    problems: list[str] = []
    if expected == "present":
        if TABLE not in tables:
            problems.append(f"table {TABLE} is missing")
        problems += [f"{TABLE}.{c} is missing" for c in CHECK_COLUMNS if c not in checks]
        problems += [f"analyses.{c} is missing" for c in ANALYSES_COLUMNS if c not in analyses]
    else:
        if TABLE in tables:
            problems.append(f"table {TABLE} survived the downgrade")
        problems += [
            f"analyses.{c} survived the downgrade" for c in ANALYSES_COLUMNS if c in analyses
        ]

    if problems:
        for problem in problems:
            print(f"FAIL: {problem}", file=sys.stderr)
        return 1

    print(f"ok: SERP schema is {expected}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("present", "absent"):
        print(f"usage: {sys.argv[0]} [present|absent]", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
