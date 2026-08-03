"""Run one analysis through the live DRY_RUN stack and assert its SERP summary.

Used by the `stack` job in serp.yml. Everything else that tests SERP does it
against SQLite in-process; this is the only check that the migration, the
worker, the pipeline wiring and the API serialization agree with each other on
a real Postgres.

Standard library only — it runs on the runner's own python3, not in the backend
virtualenv.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

# Overridable so the same check can be pointed at a stack brought up on
# non-default ports (the compose host ports are parameterized — see ADR-15).
API = f"{os.environ.get('YANKI_API_ORIGIN', 'http://localhost:8141').rstrip('/')}/api/v1"
TARGET_URL = "https://example.com"
# The pipeline crawls, calls the (mock) panel and runs the SERP pass; on a cold
# runner that is comfortably under two minutes, so this is a generous ceiling.
TIMEOUT_SECONDS = 300
POLL_SECONDS = 3


def _post(path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def _get(path: str) -> dict:
    with urllib.request.urlopen(f"{API}{path}", timeout=30) as response:
        return json.load(response)


def fail(message: str, analysis: dict | None = None) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    if analysis is not None:
        print(json.dumps(analysis, indent=2)[:4000], file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    try:
        submitted = _post("/analyses", {"url": TARGET_URL})
    except urllib.error.HTTPError as exc:
        fail(f"submit returned {exc.code}: {exc.read()[:500]!r}")
        return 1

    analysis_id = submitted["id"]
    print(f"submitted {TARGET_URL} as {analysis_id}")

    deadline = time.monotonic() + TIMEOUT_SECONDS
    analysis: dict = {}
    while time.monotonic() < deadline:
        analysis = _get(f"/analyses/{analysis_id}")
        status = analysis["status"]
        if status == "done":
            break
        if status == "failed":
            fail(f"the analysis failed: {analysis.get('error')}", analysis)
        print(f"  {status} {analysis['progress']}% ({analysis.get('current_step')})")
        time.sleep(POLL_SECONDS)
    else:
        fail(f"the analysis never finished within {TIMEOUT_SECONDS}s", analysis)

    serp = analysis["result"].get("serp")
    if serp is None:
        fail("SERP_ENABLED=1 was set, but the run reported no SERP summary", analysis)

    if serp["status"] != "ok":
        fail(f"expected a measured SERP run, got status={serp['status']!r}", analysis)
    if serp["source"] != "mock":
        fail(f"DRY_RUN must use the mock SERP source, got {serp['source']!r}", analysis)
    if serp["queries"] <= 0:
        fail("a measured run must have queried something", analysis)
    if not serp["checks"]:
        fail("the evidence table is empty — nothing was persisted", analysis)

    # ``queries`` counts the pages we could READ; ``checks`` has a row for every
    # query we ran, readable or not. Conflating the two is the exact mistake this
    # feature exists to avoid, so compare like with like: the readable rows must
    # match the denominator, and every unreadable row must also have been stored
    # (a query that vanished would look like one we never ran).
    readable = [check for check in serp["checks"] if check["hit"] is not None]
    if len(readable) != serp["queries"]:
        fail(
            f"{serp['queries']} readable queries claimed but {len(readable)} readable rows stored",
            analysis,
        )
    if len(serp["checks"]) < serp["queries"]:
        fail(
            f"{len(serp['checks'])} evidence rows for {serp['queries']} measured queries",
            analysis,
        )

    # The score must be exactly the ratio the stored evidence supports — this is
    # the invariant the whole "show our work" wedge rests on.
    expected = serp["hits"] / serp["queries"]
    if abs(serp["score"] - expected) > 1e-9:
        fail(f"score {serp['score']} does not match {serp['hits']}/{serp['queries']}", analysis)

    recorded_hits = sum(1 for check in readable if check["hit"])
    if recorded_hits != serp["hits"]:
        fail(f"summary claims {serp['hits']} hits, evidence shows {recorded_hits}", analysis)

    # Queries are generated, so they must obey the invariant that they never name
    # the brand they measure (ADR-27/ADR-28).
    company = (analysis["result"].get("kyc") or {}).get("company", "")
    if company:
        for check in serp["checks"]:
            if company.casefold() in check["query"].casefold():
                fail(f"a search query named the brand it measures: {check['query']!r}", analysis)

    print(
        f"ok: SERP measured {serp['hits']}/{serp['queries']} "
        f"(score {serp['score']:.2f}) via {serp['source']}, "
        f"{len(serp['checks'])} evidence rows"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
