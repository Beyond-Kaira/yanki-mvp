"""Worker dispatches module runs before analyses (mod-6)."""

import app.worker as worker
from app.db.models import BrandContext, ModuleRun
from app.jobs.module_kinds import JOB_KIND_KYC_EXTRACT


def test_worker_prefers_module_run_over_analysis(
    db_session, session_factory, make_analysis, settings, monkeypatch
):
    monkeypatch.setattr(worker, "SessionLocal", session_factory)

    ctx = BrandContext(org_id=None, brand="Acme")
    db_session.add(ctx)
    db_session.flush()
    module_run = ModuleRun(
        job_kind=JOB_KIND_KYC_EXTRACT,
        status="queued",
        brand_context_id=ctx.id,
        payload={"source_url": "https://acme.test/"},
    )
    db_session.add(module_run)
    make_analysis(url="https://bundle.test", status="queued")
    db_session.commit()

    calls: list[str] = []

    monkeypatch.setattr(worker, "_run_module_once", lambda *_: calls.append("module") or True)
    monkeypatch.setattr(worker, "_run_analysis_once", lambda *_: calls.append("analysis") or True)

    assert worker.run_once(settings) is True
    assert calls == ["module"]


def test_worker_falls_back_to_analysis(
    db_session, session_factory, make_analysis, settings, monkeypatch
):
    monkeypatch.setattr(worker, "SessionLocal", session_factory)

    make_analysis(url="https://bundle.test", status="queued")
    db_session.commit()

    calls: list[str] = []

    monkeypatch.setattr(worker, "_run_module_once", lambda *_: False)
    monkeypatch.setattr(
        worker,
        "_run_analysis_once",
        lambda *_: calls.append("analysis") or True,
    )

    assert worker.run_once(settings) is True
    assert calls == ["analysis"]
