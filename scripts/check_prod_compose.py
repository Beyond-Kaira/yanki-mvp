#!/usr/bin/env python3
"""Assert the production compose file bounds every service's blast radius.

This VPS runs Yanki's production stack beside four other companies' production
stacks on ~11.7 GiB of shared RAM and one shared disk. An uncapped service is
therefore not a Yanki problem: a memory leak in ``worker`` or an unbounded
``json-file`` log on ``api`` takes the co-tenants down with us. Caps are only
worth anything if they cannot be silently lost, and there are two ways to lose
them that no ordinary check notices:

  1. **A new service is added without caps.** ``docker compose config`` happily
     validates an uncapped service — being uncapped is legal, just dangerous
     here. Nothing else in CI would say a word.

  2. **The caps are written in the swarm-only form.** ``deploy.resources.limits``
     is what most documentation and most LLMs reach for, and a plain
     ``docker compose up`` — which is exactly what ``deploy/deploy.sh`` runs —
     *silently ignores it*. ``config -q`` exits 0 on that form too. The file
     would read as capped, review as capped, and enforce nothing.

So this reads the *rendered* config (post-interpolation, post-profile, the same
thing the deploy actually gets) and fails on either. Rendered input, not the raw
YAML, is the point: a cap that does not survive rendering was never a cap.

Usage:
    docker compose -f deploy/docker-compose.prod.yml config --format json \\
      | python3 scripts/check_prod_compose.py
"""

from __future__ import annotations

import json
import sys

# Below this, a normal boot is at risk of being OOM-killed, which is a worse
# outage than the one caps prevent. A typo like `mem_limit: 64` (bytes, not
# megabytes) is the realistic way this trips.
MIN_MEM_LIMIT_BYTES = 128 * 1024 * 1024


def main() -> int:
    try:
        config = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(f"could not parse the rendered compose config as JSON: {exc}", file=sys.stderr)
        return 2

    services = config.get("services") or {}
    if not services:
        print("the rendered compose config declares no services", file=sys.stderr)
        return 2

    problems: list[str] = []

    for name in sorted(services):
        service = services[name] or {}

        # The swarm-only form. If it carries limits, they are being dropped.
        deploy_limits = ((service.get("deploy") or {}).get("resources") or {}).get("limits")
        if deploy_limits:
            problems.append(
                f"{name}: uses the swarm-only `deploy.resources.limits` form "
                f"({deploy_limits}), which a plain `docker compose up` silently "
                f"ignores. Use top-level `mem_limit` / `cpus` instead."
            )

        mem_limit = service.get("mem_limit")
        if not mem_limit:
            problems.append(
                f"{name}: no `mem_limit`. Every service on this shared box needs "
                f"a ceiling, or one leak starves the co-tenants."
            )
        elif isinstance(mem_limit, int) and mem_limit < MIN_MEM_LIMIT_BYTES:
            problems.append(
                f"{name}: `mem_limit` is {mem_limit} bytes, below the "
                f"{MIN_MEM_LIMIT_BYTES}-byte floor — almost certainly a unit typo, "
                f"and it would OOM-kill the service on boot."
            )

        options = (service.get("logging") or {}).get("options") or {}
        if not options.get("max-size"):
            problems.append(
                f"{name}: no bounded log driver (`logging.options.max-size`). "
                f"An unbounded json-file log fills the shared disk."
            )

    if problems:
        print("deploy/docker-compose.prod.yml is not safe for the shared VPS:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(f"all {len(services)} prod services are memory-capped and log-bounded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
