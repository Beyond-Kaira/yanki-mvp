"""Postgres-as-queue: claim the next analysis to run.

The ``analyses`` table *is* the queue. One transaction selects the oldest row
that is either ``queued`` or a stale ``running`` (crashed worker), locks it with
``FOR UPDATE SKIP LOCKED`` so concurrent workers never grab the same row, and
marks it ``running``. On SQLite (used by the unit tests) there is no
``SKIP LOCKED``, so we fall back to a plain SELECT + UPDATE — tests are
single-threaded so no locking is needed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Analysis

MAX_ATTEMPTS = 3


def _finalize_claim(session: Session, analysis: Analysis, now: datetime) -> Analysis | None:
    analysis.attempts += 1

    if analysis.attempts > MAX_ATTEMPTS:
        analysis.status = "failed"
        analysis.error = "max retries exceeded"
        analysis.claimed_at = now
        session.commit()
        return None

    analysis.status = "running"
    analysis.claimed_at = now
    session.commit()
    return analysis


def claim_analysis_by_id(
    session: Session,
    analysis_id: uuid.UUID,
    settings: Settings,
) -> Analysis | None:
    """Claim one analysis by id when Redis dispatch pointed the worker at it.

    Returns None when the row is absent, already terminal, or actively running
    on another worker — so duplicate Redis deliveries are harmless.
    """

    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=settings.stale_claim_seconds)

    stmt = (
        select(Analysis)
        .where(
            Analysis.id == analysis_id,
            or_(
                Analysis.status == "queued",
                and_(Analysis.status == "running", Analysis.claimed_at < cutoff),
            ),
        )
        .limit(1)
    )

    if session.get_bind().dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)

    analysis = session.execute(stmt).scalars().first()
    if analysis is None:
        return None

    return _finalize_claim(session, analysis, now)


def claim_next(session: Session, settings: Settings) -> Analysis | None:
    """Claim and return the next runnable analysis, or None if there is nothing to do.

    Increments ``attempts`` on every claim. A job whose attempts exceed
    ``MAX_ATTEMPTS`` is marked ``failed`` (poison-job guard) and None is returned.
    """
    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=settings.stale_claim_seconds)

    stmt = (
        select(Analysis)
        .where(
            # Both MVP crawl rows and checker rows (kind='checker') run through
            # this pipeline now: P5.2 branches ``run_pipeline`` on ``kind`` (a
            # checker row seeds KYC from its brand+category instead of crawling
            # its synthetic ``checker://`` url), so the worker claims every kind.
            or_(
                Analysis.status == "queued",
                and_(Analysis.status == "running", Analysis.claimed_at < cutoff),
            ),
        )
        .order_by(Analysis.created_at)
        .limit(1)
    )

    # SKIP LOCKED is a Postgres feature; SQLite tests use the plain path.
    if session.get_bind().dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)

    analysis = session.execute(stmt).scalars().first()
    if analysis is None:
        return None

    return _finalize_claim(session, analysis, now)
