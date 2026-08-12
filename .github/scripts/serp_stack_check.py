"""Run one analysis through the live DRY_RUN stack and assert its SERP summary.

Used by the `stack` job in serp.yml. Everything else that tests SERP does it
against SQLite in-process; this is the only check that the migration, the
worker, the pipeline wiring and the API serialization agree with each other on
a real Postgres.

**It signs in first, because since P7.6 there is no anonymous way in** (ADR-45).
`POST /analyses` requires a bearer, and `GET /analyses/{id}` will only return a
run to the organization that owns it — an analysis that carries an `org_id` is
no longer a capability URL. Both halves of this check therefore run as a real
account that this script creates on the throwaway stack. When the run finishes,
SERP evidence is read from ``GET /analyses/{id}/serp`` (the main GET is a thin
poll envelope since the analysis API read split, phase 2).

That also means this check now exercises something it never used to: sign-up,
sign-in, the permission gate, and the plan quota, on a real Postgres. A fresh
organization falls back to the Free plan, whose monthly analysis allowance is
comfortably more than the one run made here.

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
import uuid

# Overridable so the same check can be pointed at a stack brought up on
# non-default ports (the compose host ports are parameterized — see ADR-15).
API = f"{os.environ.get('YANKI_API_ORIGIN', 'http://localhost:8141').rstrip('/')}/api/v1"
TARGET_URL = "https://example.com"
# Unique per run so a re-run against a stack that was not torn down does not
# collide with the previous account (409 on signup).
ACCOUNT_EMAIL = f"serp-stack-check+{uuid.uuid4().hex[:12]}@example.com"
ACCOUNT_PASSWORD = uuid.uuid4().hex
# The pipeline crawls, calls the (mock) panel and runs the SERP pass; on a cold
# runner that is comfortably under two minutes, so this is a generous ceiling.
TIMEOUT_SECONDS = 300
POLL_SECONDS = 3


def _headers(token: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _post(path: str, payload: dict, token: str | None = None) -> dict:
    request = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers=_headers(token),
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def _get(path: str, token: str | None = None) -> dict | None:
    request = urllib.request.Request(f"{API}{path}", headers=_headers(token), method="GET")
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.load(response)
    if body is None:
        return None
    if not isinstance(body, dict):
        fail(f"GET {path} returned unexpected JSON: {type(body).__name__!r}")
    return body


def fail(message: str, analysis: dict | None = None) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    if analysis is not None:
        print(json.dumps(analysis, indent=2)[:4000], file=sys.stderr)
    raise SystemExit(1)


def sign_in() -> str:
    """Create an account on the throwaway stack and return its access token."""

    credentials = {"email": ACCOUNT_EMAIL, "password": ACCOUNT_PASSWORD}
    try:
        _post("/auth/signup", credentials)
    except urllib.error.HTTPError as exc:
        fail(f"signup returned {exc.code}: {exc.read()[:500]!r}")

    try:
        session = _post("/auth/login", credentials)
    except urllib.error.HTTPError as exc:
        # A 503 here is almost always a stack with no JWT_SECRET_KEY, which is
        # set by the workflow step that writes deploy/.env.
        fail(f"login returned {exc.code}: {exc.read()[:500]!r}")

    token = session.get("access_token")
    if not token:
        fail("login succeeded but returned no access token")
    print(f"signed in as {ACCOUNT_EMAIL}")
    return str(token)


def main() -> int:
    token = sign_in()

    try:
        submitted = _post("/analyses", {"url": TARGET_URL}, token)
    except urllib.error.HTTPError as exc:
        fail(f"submit returned {exc.code}: {exc.read()[:500]!r}")
        return 1

    analysis_id = submitted["id"]
    print(f"submitted {TARGET_URL} as {analysis_id}")

    deadline = time.monotonic() + TIMEOUT_SECONDS
    analysis: dict = {}
    while time.monotonic() < deadline:
        envelope = _get(f"/analyses/{analysis_id}", token)
        if envelope is None:
            fail(f"GET /analyses/{analysis_id} returned empty body")
        analysis = envelope
        status = analysis["status"]
        if status == "done":
            break
        if status == "failed":
            fail(f"the analysis failed: {analysis.get('error')}", analysis)
        print(f"  {status} {analysis['progress']}% ({analysis.get('current_step')})")
        time.sleep(POLL_SECONDS)
    else:
        fail(f"the analysis never finished within {TIMEOUT_SECONDS}s", analysis)

    # Phase 2: the poll envelope is thin; feature payloads live on slice routes.
    serp = _get(f"/analyses/{analysis_id}/serp", token)
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
    kyc_out = _get(f"/analyses/{analysis_id}/kyc", token) or {}
    company = (kyc_out.get("kyc") or {}).get("company", "")
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
