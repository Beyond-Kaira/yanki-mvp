#!/usr/bin/env python3
"""One-shot live DataForSEO SERP query — for credential / payload validation.

Loads ``deploy/.env`` (then process env overrides) and runs one query through
the same registry path the pipeline uses. Does not touch the database.

    cd backend && uv run python ../scripts/spike/dataforseo_serp.py "best crm software"
"""

from __future__ import annotations

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


def main() -> int:
    _load_deploy_env()
    sys.path.insert(0, str(ROOT / "backend"))

    from app.config import get_settings
    from app.serp.registry import get_serp_source

    get_settings.cache_clear()

    query = " ".join(sys.argv[1:]).strip() or "best crm software"
    settings = get_settings()
    # Spike always hits the real API — override dry_run for this process only.
    settings = settings.model_copy(update={"dry_run": False, "serp_enabled": True})

    source = get_serp_source(settings)
    if source is None:
        print(
            "No SERP source — set SERP_PROVIDER=dataforseo and "
            "DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD in deploy/.env",
            file=sys.stderr,
        )
        return 1

    page = source.search(query)
    print(f"source={source.name!r} query={page.query!r} measurable={page.measurable}")
    print(
        f"results={len(page.results)} suggestions={len(page.suggestions)} "
        f"answers={len(page.answers)}"
    )
    for row in page.results[:5]:
        print(f"  #{row.rank} {row.title[:60]!r} → {row.url}")
    if page.suggestions:
        print("suggestions:", ", ".join(page.suggestions[:5]))
    if page.answers:
        print("answers:", ", ".join(page.answers[:3]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
