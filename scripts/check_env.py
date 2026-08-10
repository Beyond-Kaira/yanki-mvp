#!/usr/bin/env python3
"""Preflight sanity check for a deploy's environment file.

Exits non-zero only when the run is LIVE (``DRY_RUN`` off) but a variable the
live path genuinely needs is missing — the mistake that lets a deploy report
green and then have every job die at runtime for want of a key /healthz never
touches. Under ``DRY_RUN`` (the default) nothing is required, so ``make dev`` /
``make test`` keep working with zero keys and $0.

What the LIVE path actually needs (traced from backend/app/config.py and
backend/app/pipeline/execute_measured.py, not guessed):

  * JWT_SECRET_KEY  — auth fails closed while blank; login returns 503 and no
                      token can be issued or validated. Needed on every live
                      deploy regardless of GEO mode.
  * OPEN_ROUTER_KEY — every GEO audit calls the OpenRouter LLM, in both the
                      ``measured`` and ``simulated`` modes. Needed whenever
                      DRY_RUN is off.
  * TAVILY_API_KEY  — only GEO_MODE=measured runs a Tavily search per audit;
                      GEO_MODE=simulated is OpenRouter-only and does not use it.
                      execute_measured._geo_mode treats any value that is not
                      exactly ``simulated`` as ``measured``, so this check does
                      the same: Tavily is required unless the mode is simulated.

The retired four-engine provider keys (ANTHROPIC_API_KEY / OPENAI_API_KEY /
GEMINI_API_KEY / PERPLEXITY_API_KEY) are deliberately NOT checked — the measured
path does not read them, and gating a deploy on them was the original bug.

Usage:  python scripts/check_env.py [path/to/.env]   (default: deploy/.env)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

TRUTHY = {"1", "true", "yes", "on"}


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip()
    return values


def required_when_live(values: dict[str, str]) -> list[tuple[str, str]]:
    """(variable, mode-that-requires-it) pairs that must be non-empty when live."""
    reqs = [
        (
            "JWT_SECRET_KEY",
            "a live deploy (DRY_RUN=0) — auth cannot issue or validate tokens without it",
        ),
        (
            "OPEN_ROUTER_KEY",
            "a live deploy (DRY_RUN=0) — every GEO audit calls the OpenRouter LLM",
        ),
    ]
    # Mirror execute_measured._geo_mode: anything that is not exactly "simulated"
    # runs the measured (Tavily) path, so only "simulated" is exempt from Tavily.
    mode = (values.get("GEO_MODE", "measured") or "measured").strip().lower()
    if mode != "simulated":
        reqs.append(
            (
                "TAVILY_API_KEY",
                "GEO_MODE=measured (DRY_RUN=0) — each audit runs a Tavily search",
            )
        )
    return reqs


def main() -> int:
    env_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("deploy/.env")
    # Process env overrides the file (compose/host precedence).
    values = {**load_env_file(env_path), **os.environ}

    if values.get("DRY_RUN", "1").strip().lower() in TRUTHY:
        print("check_env: DRY_RUN is on — no API keys required. OK.")
        return 0

    missing = [
        (key, reason)
        for key, reason in required_when_live(values)
        if not values.get(key)
    ]
    if missing:
        print(
            "check_env: DRY_RUN is off but required variables are empty:",
            file=sys.stderr,
        )
        for key, reason in missing:
            print(f"  - {key} is required for {reason}", file=sys.stderr)
        return 1

    print("check_env: live-provider config looks complete. OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
