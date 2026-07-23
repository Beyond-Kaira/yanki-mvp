"""Reusable per-IP / global rate limiting for the public write endpoints.

P5.0 wires this into ``POST /api/v1/analyses`` — the LIVE endpoint that is
already public with real keys, so a rejection must land BEFORE any ``analyses``
row is created or money is spent. The helpers here are deliberately
endpoint-agnostic: P5.6 reuses ``hash_ip`` / ``client_ip`` (with the SAME
``ip_hash_salt`` — there is no second salt) plus ``_retry_after`` for the
anonymous ``/api/v1/checker`` endpoint. ``check_checker_rate_limit`` and
``checker_daily_cost_exceeded`` add the checker's per-IP, per-brand, and
daily-cost guards; the route calls them only for a FRESH run, because a $0 24h
cache hit is exempt from every guard (see ADR-22). Because recorded
``responses.cost_usd`` LAGS the worker (a just-enqueued run has spent nothing
yet), the cost guard also projects the spend of in-flight fresh runs at a
conservative per-run estimate whenever real keys are live, so a distinct-triple
burst cannot slip an unbounded backlog past the lagging sum (see ADR-22).

Timestamp note: ``analyses.created_at`` is ``DateTime(timezone=True)`` with a
Python-side aware default. On Postgres reads come back tz-aware; on the SQLite
test DB they come back naive (UTC wall-clock). All comparisons are anchored on
``datetime.now(UTC) - timedelta(...)`` and every datetime we do arithmetic on is
normalized to aware-UTC first, so the same code is correct on both backends.
"""

from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Analysis, CheckerSubmission, Response, WaitlistSignup

# Waitlist signups per client IP per rolling hour (P5.13). Fixed here rather than
# in Settings — the endpoint spends no money and needs no per-env tuning knob.
WAITLIST_RATE_LIMIT_PER_IP_HOUR = 10


class RateLimitExceeded(Exception):
    """Raised when a rate limit is hit.

    ``retry_after`` is seconds until the oldest counted row leaves the window
    (always >= 1), suitable for a ``Retry-After`` header. ``scope`` names the
    breached guard for logging/tests: ``"ip"`` / ``"global"`` (the analyses
    endpoint) or ``"checker_ip"`` / ``"checker_brand"`` (the checker endpoint).
    """

    def __init__(self, retry_after: int, scope: str) -> None:
        super().__init__(f"rate limit exceeded ({scope})")
        self.retry_after = retry_after
        self.scope = scope


def hash_ip(ip: str, salt: str) -> str:
    """Return the SHA-256 hex digest of ``salt + ip``.

    The salt may be empty for the MVP (privacy is best-effort); the raw IP is
    never stored either way.
    """
    return hashlib.sha256(f"{salt}{ip}".encode()).hexdigest()


def client_ip(request: Request) -> str | None:
    """Best-effort client IP.

    Prefers the first entry of ``X-Forwarded-For`` (the host nginx edge sets it
    in prod), else the socket peer. Tolerates ``request.client`` being ``None``
    (as it can be under the test client / ASGI without a peer).
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    if request.client is not None:
        return request.client.host
    return None


def _as_aware(dt: datetime) -> datetime:
    """Normalize a possibly-naive DB datetime to aware UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _retry_after(oldest: datetime, window: timedelta, now: datetime) -> int:
    """Seconds until ``oldest`` ages out of ``window`` (>= 1)."""
    remaining = (_as_aware(oldest) + window - now).total_seconds()
    return max(1, math.ceil(remaining))


def check_rate_limit(session: Session, ip_hash: str, settings: Settings) -> None:
    """Enforce BOTH limits on the ``analyses`` table; raise on breach.

    - Per-IP: reject when this ``ip_hash`` already has
      ``analyses_rate_limit_per_ip_hour`` rows created in the last hour;
      ``Retry-After`` is the time until the oldest of those rows leaves the
      1-hour window.
    - Global: reject when ALL IPs together already created
      ``analyses_daily_cap`` rows in the last 24h (a rolling window — the
      simplest defensible reading of "daily"); ``Retry-After`` is the time until
      the oldest counted row leaves the 24h window.

    Must be called BEFORE ``create_analysis`` so a rejected client never gets a
    row (and 422-rejected submits, which create no row, never count).
    """
    now = datetime.now(UTC)

    # --- Per-IP hourly limit -------------------------------------------------
    hour_window = timedelta(hours=1)
    ip_rows = (
        session.execute(
            select(Analysis.created_at)
            .where(
                Analysis.ip_hash == ip_hash,
                Analysis.created_at >= now - hour_window,
            )
            .order_by(Analysis.created_at)
        )
        .scalars()
        .all()
    )
    if len(ip_rows) >= settings.analyses_rate_limit_per_ip_hour:
        # A limit of 0 rejects every submit (kill-switch); there is no oldest
        # row to age out then, so Retry-After falls back to the full window.
        retry = (
            _retry_after(ip_rows[0], hour_window, now)
            if ip_rows
            else int(hour_window.total_seconds())
        )
        raise RateLimitExceeded(retry, "ip")

    # --- Global daily cap (rolling 24h across all IPs) -----------------------
    day_window = timedelta(hours=24)
    day_count = session.execute(
        select(func.count())
        .select_from(Analysis)
        .where(Analysis.created_at >= now - day_window)
    ).scalar_one()
    if day_count >= settings.analyses_daily_cap:
        oldest_of_day = session.execute(
            select(Analysis.created_at)
            .where(Analysis.created_at >= now - day_window)
            .order_by(Analysis.created_at)
            .limit(1)
        ).scalar_one_or_none()
        retry = (
            _retry_after(oldest_of_day, day_window, now)
            if oldest_of_day is not None
            else int(day_window.total_seconds())
        )
        raise RateLimitExceeded(retry, "global")


def check_checker_rate_limit(
    session: Session,
    ip_hash: str,
    triple: tuple[str, str, str],
    settings: Settings,
) -> None:
    """Enforce the checker's per-IP and per-brand limits; raise on breach.

    - Per-IP: reject when this ``ip_hash`` already has
      ``checker_rate_limit_per_ip_hour`` rows in ``checker_submissions`` created
      in the last rolling hour. The counter includes any cache-hit submissions
      the IP made (they are real rows), bounding one IP's total demand.
    - Per-brand: reject when this normalized ``(brand, category, lang)`` already
      has ``checker_rate_limit_per_brand_day`` FRESH runs (``kind='checker'``
      ``analyses`` rows) created in the last rolling day — the guard against one
      hot brand hammered from many IPs. A cache-served repeat creates no
      ``analyses`` row, so it neither counts nor is counted here.

    Both use the ``>=`` idiom of ``check_rate_limit`` so a limit of ``0`` is a
    clean kill-switch (rejects every fresh submit, never a 500 on the empty
    window). ``Retry-After`` is the time until the oldest counted row ages out.

    The route calls this ONLY for a fresh submit: a $0 cache hit is exempt from
    every guard so it always returns its id for the email gate (ADR-22). Call it
    BEFORE ``create_checker_analysis`` so a rejected client records nothing.
    """
    now = datetime.now(UTC)

    # --- Per-IP hourly limit (submission rows) -------------------------------
    hour_window = timedelta(hours=1)
    ip_rows = (
        session.execute(
            select(CheckerSubmission.created_at)
            .where(
                CheckerSubmission.ip_hash == ip_hash,
                CheckerSubmission.created_at >= now - hour_window,
            )
            .order_by(CheckerSubmission.created_at)
        )
        .scalars()
        .all()
    )
    if len(ip_rows) >= settings.checker_rate_limit_per_ip_hour:
        retry = (
            _retry_after(ip_rows[0], hour_window, now)
            if ip_rows
            else int(hour_window.total_seconds())
        )
        raise RateLimitExceeded(retry, "checker_ip")

    # --- Per-brand daily limit (fresh checker runs of this triple) -----------
    nbrand, ncategory, nlang = triple
    day_window = timedelta(hours=24)
    brand_rows = (
        session.execute(
            select(Analysis.created_at)
            .where(
                Analysis.kind == "checker",
                Analysis.brand == nbrand,
                Analysis.category == ncategory,
                Analysis.lang == nlang,
                Analysis.created_at >= now - day_window,
            )
            .order_by(Analysis.created_at)
        )
        .scalars()
        .all()
    )
    if len(brand_rows) >= settings.checker_rate_limit_per_brand_day:
        retry = (
            _retry_after(brand_rows[0], day_window, now)
            if brand_rows
            else int(day_window.total_seconds())
        )
        raise RateLimitExceeded(retry, "checker_brand")


def check_waitlist_rate_limit(session: Session, ip_hash: str, limit: int) -> None:
    """Enforce the waitlist's per-IP hourly limit; raise on breach.

    Reuses the ``check_rate_limit`` idiom: count this ``ip_hash``'s rows created
    in the last rolling hour and reject once they reach ``limit`` (``>=`` so a
    ``limit`` of 0 is a clean kill-switch, never a 500 on the empty window).
    ``Retry-After`` is the time until the oldest counted row ages out. Because a
    duplicate email inserts no row (ON CONFLICT DO NOTHING), the counter tracks
    genuinely recorded signups from the IP — the same "count the rows" shape as
    the analyses and checker guards.
    """
    now = datetime.now(UTC)
    hour_window = timedelta(hours=1)
    ip_rows = (
        session.execute(
            select(WaitlistSignup.created_at)
            .where(
                WaitlistSignup.ip_hash == ip_hash,
                WaitlistSignup.created_at >= now - hour_window,
            )
            .order_by(WaitlistSignup.created_at)
        )
        .scalars()
        .all()
    )
    if len(ip_rows) >= limit:
        retry = (
            _retry_after(ip_rows[0], hour_window, now)
            if ip_rows
            else int(hour_window.total_seconds())
        )
        raise RateLimitExceeded(retry, "waitlist_ip")


# Conservative planning estimate of ONE fresh checker run's LLM cost, used only
# to project the spend of runs already enqueued but not yet costed by the worker
# (see ``checker_daily_cost_exceeded``). Derived from the panel shape — roughly
# ``PROMPT_COUNT`` prompts fanned across the paid engines, with Claude Haiku
# ($1/$5 per 1M in/out tokens) dominating — and rounded up so the projection
# errs toward refusing. It only needs to stay within a small factor of the true
# per-run cost: the backstop bounds concurrently in-flight fresh runs to about
# ``cap / this value``, so any drift caps backlog overshoot at a small multiple
# of the cap rather than leaving it unbounded. Retune alongside the price tables
# (and when P5.7 turns Gemini/Perplexity from $0 stubs into real spend).
_EST_CHECKER_RUN_COST_USD = 0.05


def checker_daily_cost_exceeded(session: Session, settings: Settings) -> bool:
    """Return True when today's checker spend has reached the daily cap.

    Sums ``responses.cost_usd`` over rows belonging to ``kind='checker'``
    analyses within a rolling 24h window (the same window shape as the analyses
    daily cap — the simplest defensible reading of "today", avoiding a
    UTC-midnight reset cliff and any timezone-of-record question; see ADR-22).

    Recorded cost LAGS actual spend: the guard runs at submit time but a run's
    ``responses`` are written by the worker later, so a just-enqueued run counts
    as $0 until it finishes. Without a backstop, a distinct-triple burst (each
    triple evading the per-brand cap, each spoofed IP evading the per-IP cap)
    could enqueue an unbounded backlog past this lagging sum, which the worker
    would then spend far past the cap. So with real keys live the guard also
    PROJECTS in-flight fresh runs (``kind='checker'`` analyses still ``queued``
    or ``running`` in the window) at ``_EST_CHECKER_RUN_COST_USD`` each, bounding
    the concurrently enqueued backlog to about ``cap / est``. The projection is
    deliberately skipped under ``DRY_RUN``: there every run completes at $0, so
    projecting a phantom cost would wrongly trip the cap — instead the recorded
    sum stays 0 and any positive cap never trips, exactly as the card requires.
    (A ``running`` run whose partial cost is already summed is also projected in
    full; that double-count is an intentional, documented safety margin.)

    Uses ``>=`` so a cap of ``0`` refuses every fresh run (kill-switch idiom).
    The route calls this ONLY for a fresh run; a $0 cache hit is exempt.
    """
    now = datetime.now(UTC)
    day_window = timedelta(hours=24)
    recorded = session.execute(
        select(func.coalesce(func.sum(Response.cost_usd), 0))
        .select_from(Response)
        .join(Analysis, Response.analysis_id == Analysis.id)
        .where(
            Analysis.kind == "checker",
            Response.created_at >= now - day_window,
        )
    ).scalar_one()
    projected = float(recorded)

    if not settings.dry_run:
        in_flight = session.execute(
            select(func.count())
            .select_from(Analysis)
            .where(
                Analysis.kind == "checker",
                Analysis.status.in_(("queued", "running")),
                Analysis.created_at >= now - day_window,
            )
        ).scalar_one()
        projected += in_flight * _EST_CHECKER_RUN_COST_USD

    return projected >= settings.checker_daily_usd_cap
