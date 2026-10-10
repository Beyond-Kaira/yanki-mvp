"""Worker Redis dispatch claim path."""

import app.worker as worker
from app.jobs import redis_dispatch_queue


class FakeRedisDispatch(redis_dispatch_queue.PostgresFallbackDispatch):
    def __init__(self, job_ids: list[str]) -> None:
        self._job_ids = list(job_ids)

    def try_pop(self, queue: str) -> str | None:
        if queue != redis_dispatch_queue.QUEUE_ANALYSIS or not self._job_ids:
            return None
        return self._job_ids.pop(0)


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
