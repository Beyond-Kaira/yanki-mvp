"""Queue mechanics: claim order, SQLite fallback, stale reclaim, retry cap.

These run against SQLite (the plain SELECT + UPDATE path). The Postgres-only
``FOR UPDATE SKIP LOCKED`` behaviour is exercised in the live stack; here we
verify the portable logic that both paths share.
"""

from datetime import UTC, datetime, timedelta

from app.jobs.queue import claim_analysis_by_id, claim_next


def _dt(offset_seconds: int = 0) -> datetime:
    return datetime.now(UTC) + timedelta(seconds=offset_seconds)


def test_claim_next_returns_oldest_queued_first(db_session, make_analysis, settings):
    older = make_analysis(url="https://older.test", created_at=_dt(-100))
    newer = make_analysis(url="https://newer.test", created_at=_dt(-10))

    first = claim_next(db_session, settings)
    assert first is not None
    assert first.id == older.id
    assert first.status == "running"
    assert first.attempts == 1
    assert first.claimed_at is not None

    second = claim_next(db_session, settings)
    assert second is not None
    assert second.id == newer.id


def test_claim_next_returns_none_when_no_work(db_session, settings):
    assert claim_next(db_session, settings) is None


def test_claim_next_claims_checker_rows(db_session, make_analysis, settings):
    # P5.2 branches run_pipeline on kind, so the worker now runs checker rows
    # too. A queued kind='checker' row must be claimed by ordinary FIFO order —
    # the P5.1 skip-guard (tech-debt #19) is gone.
    checker = make_analysis(
        url="checker://nike/running shoes",
        kind="checker",
        brand="nike",
        category="running shoes",
        lang="en",
        created_at=_dt(-200),  # oldest: claimed first
    )
    mvp = make_analysis(url="https://mvp.test", created_at=_dt(-10))

    first = claim_next(db_session, settings)
    assert first is not None
    assert first.id == checker.id  # oldest runnable row wins, checker included
    assert first.status == "running"
    assert first.attempts == 1

    second = claim_next(db_session, settings)
    assert second is not None
    assert second.id == mvp.id


def test_claim_next_uses_plain_update_on_sqlite(db_session, make_analysis, settings):
    # SQLite has no SKIP LOCKED; the claim must still succeed via the fallback branch.
    assert db_session.get_bind().dialect.name == "sqlite"
    make_analysis(url="https://a.test", created_at=_dt(-5))

    claimed = claim_next(db_session, settings)
    assert claimed is not None
    assert claimed.status == "running"


def test_stale_running_job_is_reclaimed(db_session, make_analysis, settings):
    stale = make_analysis(
        url="https://stale.test",
        status="running",
        attempts=1,
        created_at=_dt(-1000),
        claimed_at=_dt(-settings.stale_claim_seconds - 60),
    )

    claimed = claim_next(db_session, settings)
    assert claimed is not None
    assert claimed.id == stale.id
    assert claimed.attempts == 2


def test_fresh_running_job_is_not_reclaimed(db_session, make_analysis, settings):
    make_analysis(
        url="https://fresh.test",
        status="running",
        attempts=1,
        created_at=_dt(-1000),
        claimed_at=_dt(-1),
    )

    assert claim_next(db_session, settings) is None


def test_claim_analysis_by_id_claims_queued_row(db_session, make_analysis, settings):
    analysis = make_analysis(url="https://target.test", status="queued", created_at=_dt(-5))

    claimed = claim_analysis_by_id(db_session, analysis.id, settings)

    assert claimed is not None
    assert claimed.id == analysis.id
    assert claimed.status == "running"
    assert claimed.attempts == 1


def test_claim_analysis_by_id_returns_none_for_done_row(db_session, make_analysis, settings):
    analysis = make_analysis(url="https://done.test", status="done", created_at=_dt(-5))

    assert claim_analysis_by_id(db_session, analysis.id, settings) is None


def test_attempts_over_three_marks_failed(db_session, make_analysis, settings):
    poison = make_analysis(
        url="https://poison.test",
        status="running",
        attempts=3,
        created_at=_dt(-1000),
        claimed_at=_dt(-settings.stale_claim_seconds - 60),
    )

    result = claim_next(db_session, settings)

    assert result is None
    assert poison.status == "failed"
    assert poison.error == "max retries exceeded"
