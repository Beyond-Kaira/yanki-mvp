"""Background worker: poll the queue, run the pipeline, record the outcome.

The worker is the same Docker image as the api, started with a different command
(``python -m app.worker``). It owns no HTTP surface — it just claims one job at a
time and runs the six pipeline steps. Heartbeats and per-step progress are handled
inside ``run_pipeline``; here we only claim, run, and mark done/failed.

Standalone module runs (``module_runs`` table, mod-6) are claimed first so
module-scoped jobs do not sit behind a long monolith backlog. Failures there are
isolated from the ``analyses`` queue.

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
from app.db.models import Analysis, ModuleRun
from app.db.session import SessionLocal
from app.jobs.module_queue import claim_next_module_run
from app.jobs.queue import claim_next
from app.services import audit
from app.services.analyses import (
    cost_breakdown,
    purge_analysis,
    settle_cost,
    should_auto_purge_failed,
)
from app.services.emailer import send_run_alert
from app.services.tenancy import OrgContext

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


def _record_terminal_event(session, analysis: Analysis) -> None:
    """Write the immutable outcome and provider/model cost snapshot.

    The start event cannot know the bill yet. A separate terminal event keeps
    the log append-only and also preserves failed-run spend before the worker's
    optional auto-purge removes partial analysis rows.
    """

    failed = analysis.status == "failed"
    action = "analysis:failed" if failed else "analysis:complete"
    try:
        audit.emit(
            session,
            action=action,
            context=OrgContext(org_id=analysis.org_id, is_system=True),
            actor_type="job",
            actor_label="analysis worker",
            entity_type="analysis",
            entity_id=analysis.id,
            after={
                "url": analysis.url,
                "status": analysis.status,
                "kind": analysis.kind or "mvp",
                "total_responses": analysis.total_responses,
            },
            outcome="error" if failed else "success",
            detail={
                "cost": cost_breakdown(session, analysis),
                **({"error": analysis.error} if failed and analysis.error else {}),
            },
        )
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("terminal audit event failed for analysis %s", analysis.id)


def _record_module_terminal_event(session, run: ModuleRun) -> None:
    failed = run.status == "failed"
    action = "module_run:failed" if failed else "module_run:complete"
    try:
        audit.emit(
            session,
            action=action,
            context=OrgContext(org_id=run.org_id, is_system=True),
            actor_type="job",
            actor_label="module worker",
            entity_type="module_run",
            entity_id=run.id,
            after={
                "job_kind": run.job_kind,
                "status": run.status,
                "brand_context_id": run.brand_context_id,
                "linked_analysis_id": run.linked_analysis_id,
            },
            outcome="error" if failed else "success",
            detail={"error": run.error} if failed and run.error else None,
        )
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("terminal audit event failed for module run %s", run.id)


def _run_analysis_once(session, settings: Settings) -> bool:
    analysis = claim_next(session, settings)
    if analysis is None:
        return False

    analysis_id: uuid.UUID = analysis.id
    try:
        from app.pipeline.runner import (
            is_guided_measure_job,
            run_execute_prompts_and_score,
            run_pipeline,
        )

        if is_guided_measure_job(analysis):
            run_execute_prompts_and_score(session, analysis_id, settings)
        else:
            run_pipeline(session, analysis_id, settings)
    except Exception as exc:
        session.rollback()
        failed = session.get(Analysis, analysis_id)
        if failed is not None:
            failed.status = "failed"
            failed.error = str(exc)[:500]
            session.commit()
            _record_terminal_event(session, failed)
            _settle(session, failed)
            _alert(failed, settings)
            if should_auto_purge_failed(failed):
                purge_analysis(session, failed)
        logger.exception("analysis %s failed", analysis_id)
        return True

    done = session.get(Analysis, analysis_id)
    if done is not None:
        if done.status == "running":
            done.status = "done"
            done.progress = 100
            done.current_step = None
            session.commit()
        if done.status in ("done", "failed"):
            _record_terminal_event(session, done)
            _settle(session, done)
            _alert(done, settings)
        elif done.status == "awaiting_review":
            _settle(session, done)
    return True


def _run_module_once(session, settings: Settings) -> bool:
    run = claim_next_module_run(session, settings)
    if run is None:
        return False

    run_id = run.id
    try:
        from app.pipeline.module_handlers import run_module_run

        run_module_run(session, run_id, settings)
    except Exception:
        # Handler marks failed and commits on expected errors; unexpected ones too.
        logger.exception("module run %s failed", run_id)

    finished = session.get(ModuleRun, run_id)
    if finished is not None and finished.status in ("done", "failed"):
        _record_module_terminal_event(session, finished)
    return True


def run_once(settings: Settings) -> bool:
    """Claim and run at most one job. Returns True if a job was processed."""
    session = SessionLocal()
    try:
        if _run_module_once(session, settings):
            return True
        return _run_analysis_once(session, settings)
    finally:
        session.close()


def main() -> None:
    settings = get_settings()
    logger.info("worker starting (dry_run=%s)", settings.dry_run)
    while True:
        health.beat(settings)
        try:
            run_once(settings)
        except Exception:
            logger.exception("worker loop error")
        time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
