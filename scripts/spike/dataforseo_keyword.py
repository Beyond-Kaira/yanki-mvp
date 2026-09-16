#!/usr/bin/env python3
"""Live keyword expand + rank-check smoke — credential / payload validation.

Loads ``deploy/.env``, forces ``DRY_RUN=0`` and ``KEYWORD_ENABLED=1``, then
runs the same registry path as ``POST /api/v1/keywords/expand`` and an optional
rank-check. Does not touch the database.

    cd backend && uv run python ../scripts/spike/dataforseo_keyword.py

    cd backend && uv run python ../scripts/spike/dataforseo_keyword.py \\
        "best crm software" --domain acme.com --rank-queries "best crm software"
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOY_ENV = ROOT / "deploy" / ".env"


def _load_deploy_env() -> None:
    if not DEPLOY_ENV.exists():
        return
    for raw in DEPLOY_ENV.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = val.strip()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DataForSEO keyword live smoke")
    parser.add_argument(
        "seed",
        nargs="?",
        default="best crm software",
        help="Seed phrase for expand (default: best crm software)",
    )
    parser.add_argument(
        "--domain",
        default="",
        help="Optional domain for rank-check (bare host or URL)",
    )
    parser.add_argument(
        "--rank-queries",
        default="",
        help="Comma-separated queries for rank-check (default: same as seed)",
    )
    parser.add_argument(
        "--max-ideas",
        type=int,
        default=10,
        help="Expand idea cap (default: 10 — keep smoke cheap)",
    )
    parser.add_argument(
        "--skip-rank",
        action="store_true",
        help="Only run expand, skip rank-check",
    )
    return parser.parse_args()


def main() -> int:
    _load_deploy_env()
    sys.path.insert(0, str(ROOT / "backend"))

    from app.config import get_settings
    from app.keyword.rank_check import check_keyword_ranks
    from app.keyword.registry import get_keyword_serp_source, get_keyword_source

    get_settings.cache_clear()
    args = _parse_args()

    settings = get_settings().model_copy(
        update={
            "dry_run": False,
            "keyword_enabled": True,
        }
    )

    expand_source = get_keyword_source(settings)
    if expand_source is None:
        print(
            "No keyword source — set KEYWORD_ENABLED=1, SERP_PROVIDER, and either "
            "DATAFORSEO_LOGIN/PASSWORD or SERP_BASE_URL in deploy/.env",
            file=sys.stderr,
        )
        return 1

    seed = args.seed.strip()
    print(f"=== expand (source={expand_source.name!r}, seed={seed!r}) ===")
    result = expand_source.expand(seed, max_ideas=max(1, args.max_ideas), max_variants=0)
    print(f"provider={result.provider!r} ideas={len(result.ideas)} locale={result.locale!r}")
    for idea in result.ideas[:8]:
        print(f"  [{idea.source}] {idea.phrase}")

    if args.skip_rank or not args.domain.strip():
        if not args.skip_rank and not args.domain.strip():
            print("\n(rank-check skipped — pass --domain to smoke rank-check)")
        return 0

    serp_source = get_keyword_serp_source(settings)
    if serp_source is None:
        print("Rank-check source missing despite expand source — check registry.", file=sys.stderr)
        return 1

    rank_queries = [part.strip() for part in (args.rank_queries or seed).split(",") if part.strip()]
    print(
        f"\n=== rank-check (source={serp_source.name!r}, domain={args.domain!r}, "
        f"queries={rank_queries!r}) ==="
    )
    domain, hits = check_keyword_ranks(
        serp_source,
        domain=args.domain.strip(),
        queries=rank_queries,
        max_queries=min(3, len(rank_queries) or 1),
    )
    print(f"normalized_domain={domain!r}")
    for hit in hits:
        print(
            f"  query={hit.query!r} measurable={hit.measurable} appeared={hit.appeared} "
            f"rank={hit.rank} url={hit.matched_url!r}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
