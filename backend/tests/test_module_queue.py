"""Module run queue mechanics (mod-6)."""

from datetime import UTC, datetime, timedelta

from app.db.models import ModuleRun
from app.jobs.module_kinds import JOB_KIND_KYC_EXTRACT
from app.jobs.module_queue import claim_next_module_run


def _dt(offset_seconds: int = 0) -> datetime:
    return datetime.now(UTC) + timedelta(seconds=offset_seconds)


def _make_run(db_session, **kwargs) -> ModuleRun:
    run = ModuleRun(job_kind=JOB_KIND_KYC_EXTRACT, payload={"source_url": "https://a.test/"}, **kwargs)
    db_session.add(run)
    db_session.commit()
    return run


def test_claim_next_module_run_returns_oldest_first(db_session, settings):
    older = _make_run(db_session, created_at=_dt(-100))
    newer = _make_run(db_session, created_at=_dt(-10))

    first = claim_next_module_run(db_session, settings)
    assert first is not None
    assert first.id == older.id
    assert first.status == "running"
    assert first.attempts == 1

    second = claim_next_module_run(db_session, settings)
    assert second is not None
    assert second.id == newer.id


def test_claim_next_module_run_returns_none_when_idle(db_session, settings):
    assert claim_next_module_run(db_session, settings) is None


def test_stale_module_run_is_reclaimed(db_session, settings):
    stale = _make_run(
        db_session,
        status="running",
        attempts=1,
        created_at=_dt(-1000),
        claimed_at=_dt(-settings.stale_claim_seconds - 60),
    )

    claimed = claim_next_module_run(db_session, settings)
    assert claimed is not None
    assert claimed.id == stale.id
    assert claimed.attempts == 2


def test_module_run_attempts_over_three_marks_failed(db_session, settings):
    poison = _make_run(
        db_session,
        status="running",
        attempts=3,
        created_at=_dt(-1000),
        claimed_at=_dt(-settings.stale_claim_seconds - 60),
    )

    assert claim_next_module_run(db_session, settings) is None
    assert poison.status == "failed"
    assert poison.error == "max retries exceeded"
