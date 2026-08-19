"""Guided analysis profile pause (ADR-50, phase 1)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.config import Settings
from app.db.models import Analysis, Prompt, Response
from app.pipeline import discovery
from app.services.analysis_run_mode import RUN_MODE_GUIDED, STATUS_AWAITING_REVIEW


@pytest.fixture(autouse=True)
def _lift_limits():
    from app.api.main import app
    from app.config import get_settings

    app.dependency_overrides[get_settings] = lambda: Settings(
        quota_enforcement_enabled=False,
        analyses_rate_limit_per_ip_hour=1000,
        analyses_daily_cap=1000,
        user_analysis_limit=0,
    )
    yield
    app.dependency_overrides.pop(get_settings, None)


def test_submit_guided_stores_run_mode(client, db_session, signed_in):
    signed_in()
    resp = client.post(
        "/api/v1/analyses",
        json={"url": "https://acme.test", "mode": "guided"},
    )
    assert resp.status_code == 202
    analysis = db_session.get(Analysis, uuid.UUID(resp.json()["id"]))
    assert analysis is not None
    assert analysis.run_mode == RUN_MODE_GUIDED
    assert analysis.status == "queued"


def test_submit_quick_defaults_run_mode(client, db_session, signed_in):
    signed_in()
    resp = client.post("/api/v1/analyses", json={"url": "https://acme.test"})
    assert resp.status_code == 202
    analysis = db_session.get(Analysis, uuid.UUID(resp.json()["id"]))
    assert analysis.run_mode == "quick"


def test_guided_pipeline_pauses_after_prompts(db_session, settings, monkeypatch):
    from app.pipeline import runner

    monkeypatch.setattr(
        discovery,
        "discover_detailed",
        lambda url: discovery.CrawlResult(text="Acme builds warehouse robots and tools."),
    )

    analysis = Analysis(
        url="https://example.com",
        status="running",
        run_mode=RUN_MODE_GUIDED,
    )
    db_session.add(analysis)
    db_session.flush()

    result = runner.run_pipeline(db_session, analysis.id, settings)

    assert result.status == STATUS_AWAITING_REVIEW
    assert result.progress == 45
    assert result.current_step is None
    assert result.kyc is not None
    prompts = (
        db_session.execute(select(Prompt).where(Prompt.analysis_id == analysis.id)).scalars().all()
    )
    assert len(prompts) == settings.prompt_count
    responses = (
        db_session.execute(select(Response).where(Response.analysis_id == analysis.id))
        .scalars()
        .all()
    )
    assert responses == []


def test_quick_pipeline_still_runs_execute(db_session, settings, monkeypatch):
    from app.pipeline import runner

    monkeypatch.setattr(
        discovery,
        "discover_detailed",
        lambda url: discovery.CrawlResult(text="Acme builds warehouse robots and tools."),
    )

    analysis = Analysis(url="https://example.com", status="running", run_mode="quick")
    db_session.add(analysis)
    db_session.flush()

    result = runner.run_pipeline(db_session, analysis.id, settings)

    assert result.status == "done"
    assert result.progress == 100
    responses = (
        db_session.execute(select(Response).where(Response.analysis_id == analysis.id))
        .scalars()
        .all()
    )
    assert len(responses) == settings.prompt_count


def test_worker_leaves_guided_run_awaiting_review(worker_session_factory, monkeypatch):
    import app.worker as worker
    from app.pipeline import discovery

    monkeypatch.setattr(
        discovery,
        "discover_detailed",
        lambda url: discovery.CrawlResult(text="Acme builds warehouse robots and tools."),
    )

    seed = worker_session_factory()
    analysis = Analysis(
        url="https://acme.test",
        status="queued",
        run_mode=RUN_MODE_GUIDED,
    )
    seed.add(analysis)
    seed.commit()
    analysis_id = analysis.id
    seed.close()

    settings = Settings(dry_run=True)
    assert worker.run_once(settings) is True

    check = worker_session_factory()
    try:
        row = check.get(Analysis, analysis_id)
        assert row is not None
        assert row.status == STATUS_AWAITING_REVIEW
        assert row.progress == 45
        prompts = (
            check.execute(select(Prompt).where(Prompt.analysis_id == analysis_id)).scalars().all()
        )
        assert len(prompts) == settings.prompt_count
        responses = (
            check.execute(select(Response).where(Response.analysis_id == analysis_id))
            .scalars()
            .all()
        )
        assert responses == []
    finally:
        check.close()


@pytest.fixture
def worker_session_factory(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.db.base import Base

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


def test_get_envelope_includes_run_mode(client, db_session, make_analysis):
    analysis = make_analysis(
        url="https://acme.test", status=STATUS_AWAITING_REVIEW, run_mode="guided"
    )
    body = client.get(f"/api/v1/analyses/{analysis.id}").json()
    assert body["run_mode"] == "guided"
    assert body["status"] == STATUS_AWAITING_REVIEW
