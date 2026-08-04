"""Independent Postgres-as-queue claim logic for browser-heavy Site Audits."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import SiteAudit

MAX_ATTEMPTS = 3


def claim_next_site_audit(session: Session, settings: Settings) -> SiteAudit | None:
    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=settings.site_audit_stale_claim_seconds)
    statement = (
        select(SiteAudit)
        .where(
            or_(
                SiteAudit.status == "queued",
                and_(SiteAudit.status == "running", SiteAudit.claimed_at < cutoff),
            )
        )
        .order_by(SiteAudit.created_at)
        .limit(1)
    )
    if session.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update(skip_locked=True)

    audit = session.execute(statement).scalars().first()
    if audit is None:
        return None

    audit.attempts += 1
    audit.claimed_at = now
    if audit.attempts > MAX_ATTEMPTS:
        audit.status = "failed"
        audit.error = "max retries exceeded"
        audit.completed_at = now
        session.commit()
        return None

    audit.status = "running"
    audit.error = None
    session.commit()
    return audit
