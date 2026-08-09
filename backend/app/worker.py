"""Background worker: poll the queue, run the pipeline, record the outcome.

The worker is the same Docker image as the api, started with a different command
(``python -m app.worker``). It owns no HTTP surface — it just claims one job at a
time and runs the six pipeline steps. Heartbeats and per-step progress are handled
inside ``run_pipeline``; here we only claim, run, and mark done/failed.

The pipeline package is built by a separate agent, so its import is deferred into
``run_once`` — the rest of this module (and the queue tests) import cleanly even
before the pipeline exists.
"""

from __future__ import annotations

import logging
import time
import uuid

from app import health
from app.config import Settings, get_settings
from app.db.models import Analysis
from app.db.session import SessionLocal
from app.jobs.queue import claim_next
from app.services.analyses import settle_cost
from app.services.emailer import send_run_alert

logger = logging.getLogger("yanki.worker")


def _alert(analysis: Analysis, settings: Settings) -> None:
    """Best-effort terminal-status alert (P5.13). The run is already recorded in
    ``analyses``; this email is only telemetry, so a failure or disabled email
    must NEVER change the pipeline result — hence the belt-and-braces guard even
    though ``send_run_alert`` itself never raises."""
    try:
        send_run_alert(analysis, settings)
    except Exception:
        logger.warning("run alert email failed for %s", analysis.id)


def _settle(session, analysis: Analysis) -> None:
    """Write the run's real cost into the org's credit ledger (P7.6).

    Runs on **both** terminal outcomes. A failed run that died in step five
    still paid for steps one to four, and a ledger that records only successes
    understates spend in exactly the direction that hides a problem.

    Best-effort, like the alert and for the same reason: the analysis result is
    already committed, and turning a ledger-write failure into a lost analysis
    would trade an accounting gap for a customer-visible one. Unlike the alert,
    the loss is logged at error level — this is money, and a silent gap here is
    the ADR-34 mistake wearing a different hat.
    """

    try:
        entry = settle_cost(session, analysis)
        if entry is not None:
            session.commit()
    except Exception:
        session.rollback()
        logger.exception("credit-ledger settle failed for analysis %s", analysis.id)


def run_once(settings: Settings) -> bool:
    """Claim and run at most one job. Returns True if a job was processed."""
    session = SessionLocal()
    try:
        analysis = claim_next(session, settings)
        if analysis is None:
            return False

        analysis_id: uuid.UUID = analysis.id
        try:
            from app.pipeline.runner import run_pipeline

            run_pipeline(session, analysis_id, settings)
        except Exception as exc:
            # Keep whatever partial rows earlier steps committed (FR-7); only the
            # in-flight step's uncommitted work is rolled back.
            session.rollback()
            failed = session.get(Analysis, analysis_id)
            if failed is not None:
                failed.status = "failed"
                failed.error = str(exc)[:500]
                session.commit()
                _settle(session, failed)
                _alert(failed, settings)
            logger.exception("analysis %s failed", analysis_id)
            return True

        done = session.get(Analysis, analysis_id)
        if done is not None:
            done.status = "done"
            done.progress = 100
            done.current_step = None
            session.commit()
            _settle(session, done)
            _alert(done, settings)
        return True
    finally:
        session.close()


def main() -> None:
    settings = get_settings()
    logger.info("worker starting (dry_run=%s)", settings.dry_run)
    while True:
        # Beat first, every tick, before anything that can fail. A `while True`
        # that stops looping was previously invisible — the container stays
        # "running", the queue just quietly stops draining — and the only way
        # anyone found out was noticing jobs stuck in `queued` (ADR-47).
        # `run_pipeline` beats again at each step, so a worker busy on one long
        # job is not mistaken for a dead one.
        health.beat(settings)
        try:
            run_once(settings)
        except Exception:
            logger.exception("worker loop error")
        time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
