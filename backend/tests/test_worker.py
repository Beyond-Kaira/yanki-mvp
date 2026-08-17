"""Worker outcome tests: the failed-job envelope (FR-7).

A pipeline exception must become ``status='failed'`` with the error recorded,
while partial rows earlier steps committed stay queryable. ``run_once`` owns that
translation; it is exercised here against an in-memory SQLite DB by pointing the
worker's ``SessionLocal`` at it.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db.base import Base
from app.db.models import Analysis, Prompt, Response


@pytest.fixture
def worker_session_factory(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    import app.worker as worker

    monkeypatch.setattr(worker, "SessionLocal", factory)
    yield factory
    engine.dispose()


def test_failed_job_marks_failed_and_keeps_partial_results(
    worker_session_factory, monkeypatch
):
    import app.worker as worker
    from app.pipeline import discovery, scoring
    from app.pipeline.errors import PipelineError

    # Discovery returns canned text (no network); scoring blows up AFTER kyc,
    # prompts, execute and footprint have committed their rows.
    monkeypatch.setattr(
        discovery,
        "discover_detailed",
        lambda url: discovery.CrawlResult(text="Acme builds robots."),
    )

    def _boom(records, *, reliability_score=None):
        raise PipelineError("scoring exploded")

    monkeypatch.setattr(scoring, "geo_score", _boom)

    seed = worker_session_factory()
    analysis = Analysis(url="https://example.com", status="queued")
    seed.add(analysis)
    seed.commit()
    analysis_id = analysis.id
    seed.close()

    settings = Settings(dry_run=True)  # mock providers, no network
    assert worker.run_once(settings) is True

    check = worker_session_factory()
    try:
        row = check.get(Analysis, analysis_id)
        assert row is not None
        assert row.status == "failed"
        assert row.error and "scoring exploded" in row.error

        # Partial results from the steps that DID complete survive (FR-7).
        assert row.kyc is not None
        prompts = (
            check.execute(select(Prompt).where(Prompt.analysis_id == analysis_id))
            .scalars()
            .all()
        )
        responses = (
            check.execute(select(Response).where(Response.analysis_id == analysis_id))
            .scalars()
            .all()
        )
        assert len(prompts) == settings.prompt_count
        assert len(responses) > 0
    finally:
        check.close()


def test_user_owned_failed_run_is_purged_after_worker_failure(
    worker_session_factory, monkeypatch
) -> None:
    import app.worker as worker
    from app.pipeline import discovery, scoring
    from app.pipeline.errors import PipelineError

    monkeypatch.setattr(
        discovery,
        "discover_detailed",
        lambda url: discovery.CrawlResult(text="Acme builds robots."),
    )

    def _boom(records, *, reliability_score=None):
        raise PipelineError("scoring exploded")

    monkeypatch.setattr(scoring, "geo_score", _boom)

    seed = worker_session_factory()
    user_id = uuid.uuid4()
    analysis = Analysis(
        url="https://acme.test",
        status="queued",
        org_id=uuid.uuid4(),
        created_by_user_id=user_id,
    )
    seed.add(analysis)
    seed.commit()
    analysis_id = analysis.id
    seed.close()

    settings = Settings(dry_run=True)
    assert worker.run_once(settings) is True

    check = worker_session_factory()
    try:
        assert check.get(Analysis, analysis_id) is None
    finally:
        check.close()
