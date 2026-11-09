"""Dedicated Site Audit worker; it never claims or executes GEO analyses."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime

from app.config import Settings, get_settings
from app.db.models import SiteAudit
from app.db.session import SessionLocal
from app.jobs.redis_dispatch_queue import QUEUE_SITE_AUDIT, connect_from_settings
from app.site_audit.queue import claim_by_id, claim_next_site_audit
from app.site_audit.runner import run_site_audit

logger = logging.getLogger("yanki.site_audit.worker")


def _claim_site_audit(session, settings: Settings):
    backend = connect_from_settings(settings)
    hinted = backend.try_pop(QUEUE_SITE_AUDIT)
    if hinted:
        try:
            audit_id = uuid.UUID(hinted)
        except ValueError:
            audit_id = None
        if audit_id is not None:
            claimed = claim_by_id(session, settings, audit_id)
            if claimed is not None:
                return claimed
    return claim_next_site_audit(session, settings)


def run_once(settings: Settings) -> bool:
    session = SessionLocal()
    try:
        audit = _claim_site_audit(session, settings)
        if audit is None:
            return False

        audit_id: uuid.UUID = audit.id
        try:
            run_site_audit(session, audit_id, settings)
        except Exception as exc:
            session.rollback()
            failed = session.get(SiteAudit, audit_id)
            if failed is not None:
                failed.status = "failed"
                failed.error = str(exc)[:500]
                failed.current_step = None
                failed.completed_at = datetime.now(UTC)
                session.commit()
            logger.exception("Site Audit %s failed", audit_id)
        return True
    finally:
        session.close()


def main() -> None:
    settings = get_settings()
    logger.info("Site Audit worker starting")
    while True:
        try:
            run_once(settings)
        except Exception:
            logger.exception("Site Audit worker loop error")
        time.sleep(settings.site_audit_worker_poll_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
