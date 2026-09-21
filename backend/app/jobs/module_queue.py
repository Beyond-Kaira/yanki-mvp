"""Postgres-as-queue: claim the next standalone module run (mod-6).

Mirrors ``jobs/queue.py`` for the ``module_runs`` table. Failures here do not
touch the monolith ``analyses`` queue — per-kind failure isolation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import ModuleRun

MAX_ATTEMPTS = 3


def claim_next_module_run(session: Session, settings: Settings) -> ModuleRun | None:
    """Claim and return the next runnable module job, or None if idle."""

    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=settings.stale_claim_seconds)

    stmt = (
        select(ModuleRun)
        .where(
            or_(
                ModuleRun.status == "queued",
                and_(ModuleRun.status == "running", ModuleRun.claimed_at < cutoff),
            ),
        )
        .order_by(ModuleRun.created_at)
        .limit(1)
    )

    if session.get_bind().dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)

    run = session.execute(stmt).scalars().first()
    if run is None:
        return None

    run.attempts += 1

    if run.attempts > MAX_ATTEMPTS:
        run.status = "failed"
        run.error = "max retries exceeded"
        run.claimed_at = now
        session.commit()
        return None

    run.status = "running"
    run.claimed_at = now
    run.error = None
    session.commit()
    return run
