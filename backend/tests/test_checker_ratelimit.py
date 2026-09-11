"""P5.6 hardening tests for the anonymous POST /api/v1/checker endpoint.

The checker is anonymous and, with real keys, LLM-spending, so before it can be
exposed it must be safe against a cold public URL. This suite exercises every
acceptance clause of the hardening card:

- the ``CHECKER_ENABLED`` master kill-switch (default OFF) parks a FRESH submit
  with a friendly 503 and records nothing, while a $0 24h cache hit still
  returns its id (the email gate needs a submission to attach a lead to);
- the per-IP submissions/hour and per-brand fresh-runs/day limits reject the
  ``(limit+1)``-th fresh submit with a 429 + ``Retry-After`` — a cache-served
  repeat neither counts nor is blocked;
- the daily USD cost cap refuses a fresh run with an at-capacity 503 once
  today's summed checker cost reaches it, while a cache hit still 202s;
- ``ip_hash`` is the salted hash, never the raw IP;
- a limit of 0 is a clean kill-switch (429/never a 500), consistent with P5.0;
- under DRY_RUN every cost is 0 so the default cap never trips.

Runs against the in-memory SQLite fixture like the rest of the API suite; no
worker runs, so checker cost and cache state are seeded directly into the DB.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.api.main import app
from app.config import Settings, get_settings
from app.db.models import Analysis, CheckerSubmission, Prompt, Response
from app.services.rate_limit import _EST_CHECKER_RUN_COST_USD, hash_ip


def _override_settings(**kwargs):
    """Pin route settings for a test (cleared by the client fixture teardown)."""
    settings = Settings(**kwargs)
    app.dependency_overrides[get_settings] = lambda: settings


# Wide-open limits/cap so a test can isolate ONE guard by pinning just that knob.
_OPEN = dict(
    checker_rate_limit_per_ip_hour=10_000,
    checker_rate_limit_per_brand_day=10_000,
    checker_daily_usd_cap=1_000_000.0,
)


def _submit(client, brand="nike", category="running shoes", lang="en", ip=None):
    headers = {"X-Forwarded-For": ip} if ip else {}
    return client.post(
        "/api/v1/checker",
        json={"brand": brand, "category": category, "lang": lang},
        headers=headers,
    )


def _seed_done_checker(
    db_session,
    brand="nike",
    category="running shoes",
    cost=None,
    kind="checker",
    response_age=None,
):
    """Insert a done analysis (a 24h cache hit when ``kind='checker'``).

    With ``cost`` set, also attach a prompt + response carrying that USD cost so
    the daily-cost-cap query has something to sum. ``kind`` lets a test seed a
    non-checker row (to prove the cap's ``kind='checker'`` filter excludes it),
    and ``response_age`` backdates the response's ``created_at`` (to prove the
    rolling-24h window excludes an old response). Returns the analysis row.
    """
    analysis = Analysis(
        url=f"checker://{brand}/{category}",
        status="done",
        kind=kind,
        brand=brand,
        category=category,
        lang="en",
    )
    db_session.add(analysis)
    db_session.flush()
    if cost is not None:
        prompt = Prompt(analysis_id=analysis.id, text="q", category="brand")
        db_session.add(prompt)
        db_session.flush()
        response = Response(
            analysis_id=analysis.id,
            prompt_id=prompt.id,
            llm_provider="anthropic",
            model="mock",
            raw_text="a",
            cost_usd=Decimal(str(cost)),
        )
        if response_age is not None:
            response.created_at = datetime.now(UTC) - response_age
        db_session.add(response)
    db_session.commit()
    return analysis


def _seed_queued_checker(db_session, brand):
    """Insert an in-flight (queued, kind='checker') run for ``brand`` — a fresh
    run enqueued but not yet costed by the worker. Its triple is never 'done',
    so it is not a cache hit; it exists only to exercise the cost-cap's in-flight
    projection backstop. Returns the analysis row.
    """
    analysis = Analysis(
        url=f"checker://{brand}/cat",
        status="queued",
        kind="checker",
        brand=brand,
        category="cat",
        lang="en",
    )
    db_session.add(analysis)
    db_session.commit()
    return analysis


# --- (a) kill-switch -----------------------------------------------------------


def test_killswitch_off_fresh_submit_is_parked_503_and_records_nothing(client, db_session):
    # Default posture: CHECKER_ENABLED is OFF, so a fresh submit is parked and
    # NOTHING is written (no analysis, no submission) — the public surface stays
    # dark until the operator flips the switch at go-live.
    _override_settings(checker_enabled=False, **_OPEN)
    resp = _submit(client)
    assert resp.status_code == 503
    assert db_session.query(Analysis).count() == 0
    assert db_session.query(CheckerSubmission).count() == 0


def test_killswitch_off_cached_brand_still_returns_id_and_records_submission(client, db_session):
    # A $0 24h cache hit is exempt from the kill-switch: it must still return its
    # id and record a submission so the email gate has a row to attach to.
    seeded = _seed_done_checker(db_session)
    _override_settings(checker_enabled=False, **_OPEN)

    resp = _submit(client, brand="Nike", category="Running Shoes")
    assert resp.status_code == 202
    assert resp.json()["id"] == str(seeded.id)
    # No new analysis (reused), but a fresh submission row (demand + lead target).
    assert db_session.query(Analysis).count() == 1
    assert db_session.query(CheckerSubmission).count() == 1


# --- (b) per-IP limit ----------------------------------------------------------


def test_per_ip_limit_blocks_the_limit_plus_one_fresh_submit_within_the_hour(client, db_session):
    # Fresh submits of a never-done triple all count as submissions; the
    # (limit+1)-th from one IP within the hour is rejected 429 and records
    # nothing. Per-brand is wide open so only the per-IP guard can trip.
    _override_settings(
        checker_enabled=True,
        checker_rate_limit_per_ip_hour=3,
        checker_rate_limit_per_brand_day=10_000,
        checker_daily_usd_cap=1_000_000.0,
    )
    ip = "203.0.113.7"
    for _ in range(3):
        assert _submit(client, ip=ip).status_code == 202

    resp = _submit(client, ip=ip)
    assert resp.status_code == 429
    assert 1 <= int(resp.headers["Retry-After"]) <= 3600
    # The throttled submit created no submission and no analysis.
    assert db_session.query(CheckerSubmission).count() == 3
    assert db_session.query(Analysis).count() == 3


def test_per_ip_buckets_are_independent(client):
    _override_settings(
        checker_enabled=True,
        checker_rate_limit_per_ip_hour=2,
        checker_rate_limit_per_brand_day=10_000,
        checker_daily_usd_cap=1_000_000.0,
    )
    for _ in range(2):
        assert _submit(client, ip="203.0.113.10").status_code == 202
    assert _submit(client, ip="203.0.113.10").status_code == 429  # first IP maxed
    assert _submit(client, ip="203.0.113.11").status_code == 202  # fresh bucket


# --- (c) per-brand limit -------------------------------------------------------


def test_per_brand_limit_blocks_the_limit_plus_one_fresh_run_across_ips(client):
    # The per-brand cap catches one hot brand hammered from MANY IPs: with per-IP
    # wide open, the (limit+1)-th fresh run of the same triple — from a brand-new
    # IP — is still refused 429.
    _override_settings(
        checker_enabled=True,
        checker_rate_limit_per_ip_hour=10_000,
        checker_rate_limit_per_brand_day=2,
        checker_daily_usd_cap=1_000_000.0,
    )
    assert _submit(client, brand="Hot", ip="198.51.100.1").status_code == 202
    assert _submit(client, brand="Hot", ip="198.51.100.2").status_code == 202

    resp = _submit(client, brand="Hot", ip="198.51.100.3")
    assert resp.status_code == 429
    assert 1 <= int(resp.headers["Retry-After"]) <= 24 * 3600


def test_cache_served_repeat_does_not_count_toward_per_brand(client, db_session):
    # Per-brand counts FRESH runs only. With the limit at 1 and one fresh run
    # already at the cap, a cache-served repeat is exempt: it 202s (never 429),
    # reuses the analysis, and adds no new run — so it neither counts nor blocks.
    _override_settings(
        checker_enabled=True,
        checker_rate_limit_per_ip_hour=10_000,
        checker_rate_limit_per_brand_day=1,
        checker_daily_usd_cap=1_000_000.0,
    )
    first = _submit(client)  # fresh run #1 (at the per-brand cap of 1)
    assert first.status_code == 202
    analysis_id = first.json()["id"]
    # Mark it done so the triple is now a 24h cache hit.
    row = db_session.get(Analysis, uuid.UUID(analysis_id))
    row.status = "done"
    db_session.commit()

    # Repeated cache hits keep 202-ing even though the fresh-run count is at the
    # cap, and create no new analyses (only submissions).
    for _ in range(3):
        repeat = _submit(client)
        assert repeat.status_code == 202
        assert repeat.json()["id"] == analysis_id
    assert db_session.query(Analysis).count() == 1
    assert db_session.query(CheckerSubmission).count() == 4


# --- (d) daily cost cap --------------------------------------------------------


def test_daily_cost_cap_refuses_fresh_run_but_cached_brand_still_202s(client, db_session):
    # Seed a done checker analysis whose response cost (0.50) already exceeds a
    # monkeypatched-low cap. A fresh brand+category is refused 503 at-capacity
    # and records nothing; the cached brand still 202s the existing id.
    seeded = _seed_done_checker(db_session, brand="cachedbrand", category="cat", cost="0.50")
    _override_settings(
        checker_enabled=True,
        checker_rate_limit_per_ip_hour=10_000,
        checker_rate_limit_per_brand_day=10_000,
        checker_daily_usd_cap=0.01,
    )

    fresh = _submit(client, brand="freshbrand", category="cat")
    assert fresh.status_code == 503
    # Refused fresh run recorded nothing new.
    assert db_session.query(Analysis).filter(Analysis.brand == "freshbrand").count() == 0

    cached = _submit(client, brand="cachedbrand", category="cat")
    assert cached.status_code == 202
    assert cached.json()["id"] == str(seeded.id)


def test_dry_run_zero_cost_never_trips_the_default_cap(client):
    # Under DRY_RUN there are no checker responses, so summed cost is 0 and the
    # DEFAULT cap (unpinned here) never trips: a fresh submit succeeds.
    _override_settings(checker_enabled=True)  # default cap, default limits
    assert _submit(client).status_code == 202


def test_cost_cap_ignores_out_of_window_and_non_checker_cost(client, db_session):
    # The cap sums ONLY checker responses within the rolling 24h window. Seed two
    # costly responses that must NOT count: one from a checker run whose response
    # is 25h old (outside the window), one from a non-checker (kind='mvp') run
    # inside the window. With the cap pinned below either cost, a fresh submit
    # still 202s — proving the window boundary and the kind filter both hold.
    _seed_done_checker(
        db_session, brand="oldbrand", category="cat", cost="0.50", response_age=timedelta(hours=25)
    )
    _seed_done_checker(db_session, brand="mvpbrand", category="cat", cost="0.50", kind="mvp")
    _override_settings(
        checker_enabled=True,
        checker_rate_limit_per_ip_hour=10_000,
        checker_rate_limit_per_brand_day=10_000,
        checker_daily_usd_cap=0.01,
    )
    assert _submit(client, brand="freshbrand", category="cat").status_code == 202


def test_in_flight_backlog_projection_trips_cap_with_real_keys(client, db_session):
    # Completion-lag backstop: with real keys live (dry_run=False), fresh runs
    # already enqueued but not yet costed ($0 recorded) are projected at
    # _EST_CHECKER_RUN_COST_USD each. Seed 4 queued runs and pin the cap at
    # 4*est so the projection alone reaches it; a distinct fresh brand+IP (both
    # rate limits wide open) that would otherwise sail through is refused 503 and
    # records nothing — closing the distinct-triple burst bypass.
    for i in range(4):
        _seed_queued_checker(db_session, brand=f"pending{i}")
    _override_settings(
        dry_run=False,
        checker_enabled=True,
        checker_rate_limit_per_ip_hour=10_000,
        checker_rate_limit_per_brand_day=10_000,
        checker_daily_usd_cap=4 * _EST_CHECKER_RUN_COST_USD,
    )
    resp = _submit(client, brand="freshbrand", category="cat", ip="203.0.113.90")
    assert resp.status_code == 503
    assert db_session.query(Analysis).filter(Analysis.brand == "freshbrand").count() == 0


def test_in_flight_backlog_projection_is_off_under_dry_run(client, db_session):
    # The projection is a real-keys-only backstop: under DRY_RUN every enqueued
    # run completes at $0, so the SAME backlog that trips the cap above must NOT
    # trip it here (recorded stays 0), keeping the card's "cap never trips under
    # DRY_RUN" clause literally true. A fresh submit 202s.
    for i in range(4):
        _seed_queued_checker(db_session, brand=f"pending{i}")
    _override_settings(
        dry_run=True,
        checker_enabled=True,
        checker_rate_limit_per_ip_hour=10_000,
        checker_rate_limit_per_brand_day=10_000,
        checker_daily_usd_cap=4 * _EST_CHECKER_RUN_COST_USD,
    )
    assert _submit(client, brand="freshbrand", category="cat", ip="203.0.113.91").status_code == 202


# --- (e) ip_hash is a salted hash, never the raw IP ---------------------------


def test_ip_hash_is_a_salted_hash_not_the_raw_ip(client, db_session):
    _override_settings(checker_enabled=True, **_OPEN)
    ip = "198.51.100.42"
    assert _submit(client, ip=ip).status_code == 202

    rows = db_session.query(CheckerSubmission).all()
    assert len(rows) == 1
    # Stored value is the salted hash (default empty salt), never the raw IP.
    assert rows[0].ip_hash == hash_ip(ip, "")
    assert rows[0].ip_hash != ip


# --- 0-limit kill-switch semantics, consistent with P5.0 -----------------------


def test_zero_limit_is_a_kill_switch_not_a_500(client, db_session):
    # A per-IP limit of 0 rejects every fresh submit with a clean 429 and the
    # full-window Retry-After (no oldest row to age out), never a 500 — the same
    # idiom as the analyses endpoint (test_rate_limit.py).
    _override_settings(
        checker_enabled=True,
        checker_rate_limit_per_ip_hour=0,
        checker_rate_limit_per_brand_day=10_000,
        checker_daily_usd_cap=1_000_000.0,
    )
    resp = _submit(client, ip="203.0.113.40")
    assert resp.status_code == 429
    assert int(resp.headers["Retry-After"]) == 3600

    # A per-brand limit of 0 does the same over the 24h window.
    _override_settings(
        checker_enabled=True,
        checker_rate_limit_per_ip_hour=10_000,
        checker_rate_limit_per_brand_day=0,
        checker_daily_usd_cap=1_000_000.0,
    )
    resp = _submit(client, ip="203.0.113.41")
    assert resp.status_code == 429
    assert int(resp.headers["Retry-After"]) == 24 * 3600
    # No fresh submit ever got through either kill-switch.
    assert db_session.query(Analysis).count() == 0
