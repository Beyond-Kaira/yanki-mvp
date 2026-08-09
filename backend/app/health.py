"""What `/healthz` actually checks, now that it checks anything.

Until this module existed, `/healthz` returned the literal `{"status": "ok"}`.
That is not a health check; it is a check that uvicorn is accepting sockets. It
mattered because it is the **deploy gate**: `deploy.sh` and `rollback.sh` poll it
and record `.last-good` when it answers, so a release whose database was
unreachable, whose migrations had not run, or whose plan catalog was empty
reported healthy and was recorded as the good one to roll back *to*.

Two ideas keep this honest.

**Not everything that is wrong makes a release unservable.** A backlog of queued
jobs is worth seeing and is not a reason to roll back. A missing provider key
under `DRY_RUN` is correct. So each component reports its own status and only a
named few can fail the whole probe — the ones that mean *nobody* can be served
correctly:

* the **database** — nothing works without it;
* the **plan catalog**, but only while quota enforcement is on, because an empty
  `plans` table then makes every metered route answer 503 (ADR-45). Enforcement
  off makes it harmless, and the check says so rather than crying wolf.

**The response body is load-bearing.** `deployment.sh` greps it for the
substrings `status` and `ok` rather than trusting the status code, so an
unhealthy body that happens to contain "ok" anywhere — including inside a field
name like `"ok": false`, or a word like "token" — would pass the gate it is
supposed to fail. Component states are therefore ``pass``/``fail``/``warn``, the
overall failing state is ``unhealthy``, and a test asserts the unhealthy body
contains no "ok" at all. That coupling is ugly and it is real; naming it here is
cheaper than rediscovering it during an incident.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Analysis, Plan

PASS = "pass"
WARN = "warn"
FAIL = "fail"

# Queue depth that turns a backlog into a warning. Not a failure: a burst is
# normal and rolling a release back because customers are using it would be
# absurd. Chosen well above the per-IP hourly cap (5) and the daily cap (100) is
# the real bound, so this only fires when something is genuinely not draining.
QUEUE_BACKLOG_WARN = 25
# How old the oldest queued job may be before it stops looking like a backlog
# and starts looking like nothing is consuming the queue.
QUEUE_STALE_WARN_SECONDS = 900


@dataclass
class Component:
    status: str
    detail: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"status": self.status}
        if self.detail:
            out["detail"] = self.detail
        out.update(self.data)
        return out


def _recover(session: Session) -> None:
    """Un-poison the transaction after a failed probe query.

    Postgres aborts the whole transaction on any error, so without this the
    *first* check that fails makes every check after it fail too — and the
    report would blame the database for a missing `alembic_version` table. That
    cascade does not reproduce on the SQLite test database, which is exactly why
    it is worth a named function and a comment rather than a bare `except`.
    """

    try:
        session.rollback()
    except Exception:  # pragma: no cover - nothing useful left to do
        pass


def _database(session: Session) -> Component:
    try:
        session.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - exercised by killing the DB
        # str(exc) can carry a DSN. Report the exception type only; the full
        # traceback is in the container log, which is not served over HTTP.
        _recover(session)
        return Component(FAIL, detail=f"unreachable ({type(exc).__name__})")
    return Component(PASS)


def _schema(session: Session) -> Component:
    """The migration revision the database is actually at.

    Reported, never failed on. A rollback deliberately runs older code against a
    newer schema — that is the whole reason migrations were split out of the
    api's boot command (ADR-30) — so a mismatch is normal during a rollback and
    would be the worst possible moment to refuse to serve.
    """

    try:
        revision = session.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception as exc:
        _recover(session)
        return Component(WARN, detail=f"unreadable ({type(exc).__name__})")
    if not revision:
        return Component(WARN, detail="no revision stamped")
    return Component(PASS, data={"revision": revision})


def _plans(session: Session, settings: Settings) -> Component:
    """Whether this deployment can answer "what is this org allowed to do".

    Fails the probe only while enforcement is on. With it off, an empty catalog
    changes nothing (tech-debt #76), and a health check that fails on a
    condition with no consequence trains people to ignore it.
    """

    try:
        count = session.scalar(select(func.count()).select_from(Plan)) or 0
    except Exception as exc:
        _recover(session)
        return Component(WARN, detail=f"unreadable ({type(exc).__name__})")
    if count:
        return Component(PASS, data={"count": count})
    if settings.quota_enforcement_enabled:
        return Component(FAIL, detail="catalog is empty and quota enforcement is on")
    return Component(WARN, detail="catalog is empty; enforcement is off so nothing refuses")


def _queue(session: Session) -> Component:
    """Depth and age of the analyses queue — the table IS the queue."""

    try:
        depth = (
            session.scalar(
                select(func.count()).select_from(Analysis).where(Analysis.status == "queued")
            )
            or 0
        )
        oldest = session.scalar(
            select(func.min(Analysis.created_at)).where(Analysis.status == "queued")
        )
    except Exception as exc:
        _recover(session)
        return Component(WARN, detail=f"unreadable ({type(exc).__name__})")

    data: dict[str, Any] = {"queued": depth}
    if oldest is None:
        return Component(PASS, data=data)

    # The SQLite test DB returns naive datetimes; Postgres returns aware ones.
    if oldest.tzinfo is None:
        oldest = oldest.replace(tzinfo=UTC)
    age = int((datetime.now(UTC) - oldest).total_seconds())
    data["oldest_queued_seconds"] = age

    if age > QUEUE_STALE_WARN_SECONDS:
        return Component(
            WARN, detail=f"oldest queued job is {age}s old — is the worker draining?", data=data
        )
    if depth > QUEUE_BACKLOG_WARN:
        return Component(WARN, detail=f"{depth} jobs queued", data=data)
    return Component(PASS, data=data)


def _worker(settings: Settings) -> Component:
    """Whether the worker has ticked recently.

    The worker owns no HTTP surface, so it reports liveness by touching a file
    on a volume the api also mounts. That is deliberately the cheapest thing
    that works: a heartbeat *table* would need a migration, and a heartbeat
    *endpoint* would mean giving the worker a web server to answer it.

    Absent is `warn`, not `fail`: the api runs perfectly well in environments
    with no worker at all — CI's e2e stack, a developer's laptop, the test
    suite — and a probe that fails there would teach everyone to ignore it.
    A wedged worker still shows here, which is the point: before this, a
    `while True` loop that stopped looping was invisible until somebody noticed
    jobs stuck in `queued`.
    """

    path = settings.worker_heartbeat_path
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return Component(WARN, detail="no heartbeat file — is a worker deployed?")

    age = int(time.time() - mtime)
    data = {"last_beat_seconds": age}
    if age > settings.worker_heartbeat_stale_seconds:
        return Component(
            WARN,
            detail=f"last beat {age}s ago (stale over {settings.worker_heartbeat_stale_seconds}s)",
            data=data,
        )
    return Component(PASS, data=data)


def _providers(settings: Settings) -> Component:
    """Whether the keys the LIVE measured path needs are present.

    Reported, never failed on. `DRY_RUN=1` needs none of them and is the correct
    configuration for CI and for a laptop; the deploy-time equivalent of this
    check is `scripts/check_env.py`, which *does* fail, and which is the right
    place for it because it runs before anything is replaced.
    """

    if settings.dry_run:
        return Component(PASS, data={"mode": "dry_run"})

    missing = [
        name
        for name, value in (
            ("OPEN_ROUTER_KEY", settings.open_router_key),
            ("TAVILY_API_KEY", settings.tavily_api_key),
        )
        if not value
    ]
    if missing:
        return Component(WARN, detail=f"missing: {', '.join(missing)}")
    return Component(PASS, data={"mode": "live"})


# Only these can turn the whole probe red. Everything else is information.
_FAILING_COMPONENTS = ("database", "plans")


def health_report(session: Session, settings: Settings) -> tuple[dict[str, Any], bool]:
    """Build the `/healthz` body and say whether the service is servable."""

    checks = {
        "database": _database(session),
        "schema": _schema(session),
        "plans": _plans(session, settings),
        "queue": _queue(session),
        "worker": _worker(settings),
        "providers": _providers(settings),
    }

    # A failed database makes every other DB-backed answer noise. Say so once
    # rather than printing five unreadable-because-the-database-is-down lines.
    if checks["database"].status == FAIL:
        healthy = False
    else:
        healthy = all(checks[name].status != FAIL for name in _FAILING_COMPONENTS)

    body = {
        "status": "ok" if healthy else "unhealthy",
        "checks": {name: component.as_dict() for name, component in checks.items()},
    }
    return body, healthy


def beat(settings: Settings) -> None:
    """Record one worker tick. Never raises — a heartbeat must not kill a job.

    "Never raises" is the whole contract and it is load-bearing, because this is
    called from inside the pipeline's step loop: anything it throws becomes a
    failed analysis. The catch is `Exception` rather than `OSError` on purpose.
    The first version caught only `OSError` and promptly took out sixteen
    pipeline tests, whose settings fixture is a `SimpleNamespace` without this
    field — an `AttributeError`, not an `OSError`, and a perfect illustration of
    why a best-effort side-effect must not be selective about what it forgives.

    Losing a heartbeat degrades to "no heartbeat", which `_worker` reports as a
    warning. Trading that observability gap for a failed job would be a bad
    bargain in any direction.
    """

    try:
        path = settings.worker_heartbeat_path
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w") as handle:
            handle.write(datetime.now(UTC).isoformat())
    except Exception:
        pass


__all__ = [
    "FAIL",
    "PASS",
    "QUEUE_BACKLOG_WARN",
    "QUEUE_STALE_WARN_SECONDS",
    "WARN",
    "Component",
    "beat",
    "health_report",
    "timedelta",
]
