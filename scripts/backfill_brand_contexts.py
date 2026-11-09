#!/usr/bin/env python3
"""Backfill ``brand_contexts`` from ``analyses.kyc`` and link ``brand_context_id``.

One BrandContext per eligible analysis (legacy snapshot copy). Safe to re-run: only
rows with ``brand_context_id IS NULL`` and non-empty mappable ``kyc`` are touched.

Usage:
  cd backend && uv run python ../scripts/backfill_brand_contexts.py --dry-run
  cd backend && uv run python ../scripts/backfill_brand_contexts.py --limit 100
  cd backend && uv run python ../scripts/backfill_brand_contexts.py --org-id <uuid>

Reads ``DATABASE_URL`` from ``deploy/.env`` and the environment (same as other scripts).
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
        help="Count rows that would be linked without writing",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Process at most N analyses",
    )
    parser.add_argument(
        "--org-id",
        type=uuid.UUID,
        default=None,
        help="Only analyses for this org",
    )
    args = parser.parse_args()

    _load_env()

    from app.db.session import SessionLocal
    from app.services.backfill_brand_contexts import backfill_analysis_brand_contexts

    session = SessionLocal()
    try:
        stats = backfill_analysis_brand_contexts(
            session,
            org_id=args.org_id,
            limit=args.limit,
            dry_run=args.dry_run,
        )
        if not args.dry_run:
            session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    mode = "would link" if args.dry_run else "linked"
    print(
        f"Scanned {stats.scanned} analyses; {mode} {stats.linked}; skipped {stats.skipped} (unmappable kyc)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
