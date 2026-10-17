"""Worker Redis dispatch claim path."""

import app.worker as worker
from app.jobs import redis_dispatch_queue


class FakeRedisDispatch(redis_dispatch_queue.PostgresFallbackDispatch):
    def __init__(
        self,
        job_ids: list[str] | None = None,
        *,
        queue: str = redis_dispatch_queue.QUEUE_ANALYSIS,
        module_job_ids: list[str] | None = None,
    ) -> None:
        self._queue = queue
        self._job_ids = list(job_ids or [])
        self._module_job_ids = list(module_job_ids or [])

    def try_pop(self, queue: str) -> str | None:
        if queue == redis_dispatch_queue.QUEUE_ANALYSIS and self._job_ids:
            return self._job_ids.pop(0)
        if queue == redis_dispatch_queue.QUEUE_MODULE and self._module_job_ids:
            return self._module_job_ids.pop(0)
        return None


def test_claim_analysis_prefers_redis_hint(db_session, make_analysis, settings, monkeypatch):
    analysis = make_analysis(url="https://redis.test", status="queued")
    db_session.commit()

    make_analysis(url="https://older.test", status="queued", created_at=analysis.created_at)
    db_session.commit()

    monkeypatch.setattr(
        redis_dispatch_queue,
        "connect_from_settings",
        lambda _settings: FakeRedisDispatch([str(analysis.id)]),
    )

    claimed = worker._claim_analysis(db_session, settings)
    assert claimed is not None
    assert claimed.id == analysis.id
    assert claimed.status == "running"


def test_claim_analysis_falls_back_to_db_when_redis_empty(
    db_session, make_analysis, settings, monkeypatch
):
    older = make_analysis(url="https://older.test", status="queued")
    db_session.commit()

    monkeypatch.setattr(
        redis_dispatch_queue,
        "connect_from_settings",
        lambda _settings: redis_dispatch_queue.PostgresFallbackDispatch(),
    )

    claimed = worker._claim_analysis(db_session, settings)
    assert claimed is not None
    assert claimed.id == older.id


def test_claim_module_prefers_redis_hint(db_session, settings, monkeypatch):
    from app.db.models import BrandContext, ModuleRun
    from app.jobs.module_kinds import JOB_KIND_KYC_EXTRACT

    ctx = BrandContext(org_id=None, brand="Acme")
    db_session.add(ctx)
    db_session.flush()
    run = ModuleRun(
        job_kind=JOB_KIND_KYC_EXTRACT,
        status="queued",
        brand_context_id=ctx.id,
        payload={},
    )
    db_session.add(run)
    db_session.commit()

    monkeypatch.setattr(
        redis_dispatch_queue,
        "connect_from_settings",
        lambda _settings: FakeRedisDispatch(module_job_ids=[str(run.id)]),
    )

    claimed = worker._claim_module(db_session, settings)
    assert claimed is not None
    assert claimed.id == run.id
    assert claimed.status == "running"
