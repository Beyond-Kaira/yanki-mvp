#!/usr/bin/env python3
"""Re-LPUSH queued ``module_runs`` ids to Redis ``queue:module``.

Use when rows stayed ``queued`` in Postgres but never reached Redis (LPUSH failed,
Redis was down, or dispatch was enabled after enqueue). Safe to run while workers
are up: claim is idempotent; duplicate list entries only cause extra try_pop attempts.

Usage:
  cd backend && uv run python ../scripts/redispatch_module_runs.py
  cd backend && uv run python ../scripts/redispatch_module_runs.py --dry-run

Reads ``REDIS_URL`` and ``DATABASE_URL`` from ``deploy/.env`` and the environment
(same precedence as ``check_env.py``).
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO / "backend") not in sys.path:
    sys.path.insert(0, str(_REPO / "backend"))


def _load_env() -> None:
    env_path = _REPO / "deploy" / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = val.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print ids that would be pushed without calling Redis",
    )
    args = parser.parse_args()

    _load_env()

    from sqlalchemy import select

    from app.config import get_settings
    from app.db.models import ModuleRun
    from app.db.session import SessionLocal
    from app.jobs import redis_dispatch_queue

    settings = get_settings()
    if not redis_dispatch_queue.redis_is_enabled(settings):
        print("REDIS_URL is not configured — nothing to redispatch.", file=sys.stderr)
        return 1

    session = SessionLocal()
    try:
        ids = list(
            session.scalars(
                select(ModuleRun.id)
                .where(ModuleRun.status == "queued")
                .order_by(ModuleRun.created_at)
            )
        )
    finally:
        session.close()

    if not ids:
        print("No queued module_runs found.")
        return 0

    print(f"Found {len(ids)} queued module run(s).")
    if args.dry_run:
        for run_id in ids:
            print(run_id)
        return 0

    backend = redis_dispatch_queue.connect_from_settings(settings)
    for run_id in ids:
        backend.push(redis_dispatch_queue.QUEUE_MODULE, str(run_id))
    print(f"LPUSH complete for queue:module ({len(ids)} id(s)).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
