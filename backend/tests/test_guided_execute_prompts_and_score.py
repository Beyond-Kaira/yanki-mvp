"""POST /analyses/{id}/execute-prompts-and-score — guided measure resume."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.config import Settings
from app.db.models import Analysis, AuditEvent, Prompt, Response
from app.pipeline import discovery
from app.services.analysis_run_mode import RUN_MODE_GUIDED, STATUS_AWAITING_REVIEW

EXECUTE_URL = "/api/v1/analyses/{id}/execute-prompts-and-score"


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


def _awaiting_with_prompts(db_session, user_id, org_id, *, settings) -> Analysis:
    analysis = Analysis(
        url="https://acme.test",
        status=STATUS_AWAITING_REVIEW,
        progress=45,
        run_mode=RUN_MODE_GUIDED,
        org_id=org_id,
        created_by_user_id=user_id,
        kyc={
            "company": "Acme Robotics",
            "description": "Warehouse automation",
            "industry": "Robotics",
            "category": "warehouse robots",
            "keywords": ["warehouse automation"],
            "aliases": [],
            "products": ["Acme Mover"],
            "services": [],
            "use_cases": ["warehouse automation"],
            "locations": ["Türkiye"],
            "competitors": ["Globex"],
        },
    )
    db_session.add(analysis)
    db_session.flush()
    for index in range(settings.prompt_count):
        db_session.add(
            Prompt(
                analysis_id=analysis.id,
                text=f"What are the best warehouse robots option {index}?",
                category="recommendation",
                source="generated",
                locked=False,
            )
        )
    db_session.commit()
    db_session.refresh(analysis)
    return analysis


def test_execute_prompts_and_score_queues_guided_run(client, db_session, signed_in, settings):
    user, org = signed_in()
    analysis = _awaiting_with_prompts(db_session, user.id, org.id, settings=settings)

    resp = client.post(EXECUTE_URL.format(id=analysis.id))

    assert resp.status_code == 202
    body = resp.json()
    assert body["id"] == str(analysis.id)
    assert body["status"] == "queued"
    assert body["progress"] == 45

    db_session.refresh(analysis)
    assert analysis.status == "queued"
    assert analysis.progress == 45


def test_execute_prompts_and_score_returns_409_when_not_awaiting_review(
    client, db_session, signed_in, settings, make_analysis
):
    user, org = signed_in()
    analysis = make_analysis(
        url="https://acme.test",
        status="done",
        run_mode=RUN_MODE_GUIDED,
        org_id=org.id,
        created_by_user_id=user.id,
    )

    resp = client.post(EXECUTE_URL.format(id=analysis.id))

    assert resp.status_code == 409
    assert "cannot be measured" in resp.json()["detail"]


def test_execute_prompts_and_score_returns_409_for_quick_mode(
    client, db_session, signed_in, settings
):
    user, org = signed_in()
    analysis = Analysis(
        url="https://acme.test",
        status=STATUS_AWAITING_REVIEW,
        progress=45,
        run_mode="quick",
        org_id=org.id,
        created_by_user_id=user.id,
        kyc={"company": "Acme"},
    )
    db_session.add(analysis)
    db_session.commit()

    resp = client.post(EXECUTE_URL.format(id=analysis.id))

    assert resp.status_code == 409


def test_execute_prompts_and_score_emits_audit(client, db_session, signed_in, settings):
    user, org = signed_in()
    analysis = _awaiting_with_prompts(db_session, user.id, org.id, settings=settings)

    resp = client.post(EXECUTE_URL.format(id=analysis.id))
    assert resp.status_code == 202

    event = db_session.execute(
        select(AuditEvent).where(
            AuditEvent.entity_id == analysis.id,
            AuditEvent.action == "analysis:execute_prompts_and_score",
        )
    ).scalar_one()
    assert event.after["status"] == "queued"


def test_worker_runs_measure_only_after_execute_enqueue(
    worker_session_factory, monkeypatch, settings
):
    import app.worker as worker

    crawl_calls: list[str] = []

    def _track_crawl(url):
        crawl_calls.append(url)
        return discovery.CrawlResult(text="Acme builds warehouse robots and tools.")

    monkeypatch.setattr(discovery, "discover_detailed", _track_crawl)

    seed = worker_session_factory()
    analysis = Analysis(
        url="https://acme.test",
        status="queued",
        progress=45,
        run_mode=RUN_MODE_GUIDED,
        kyc={
            "company": "Acme Robotics",
            "description": "Warehouse automation",
            "industry": "Robotics",
            "category": "warehouse robots",
            "keywords": ["warehouse automation"],
            "aliases": [],
            "products": ["Acme Mover"],
            "services": [],
            "use_cases": ["warehouse automation"],
            "locations": ["Türkiye"],
            "competitors": ["Globex"],
        },
    )
    seed.add(analysis)
    seed.flush()
    for index in range(settings.prompt_count):
        seed.add(
            Prompt(
                analysis_id=analysis.id,
                text=f"What are the best warehouse robots option {index}?",
                category="recommendation",
                source="generated",
            )
        )
    seed.commit()
    analysis_id = analysis.id
    seed.close()

    dry_settings = Settings(dry_run=True, prompt_count=settings.prompt_count)
    assert worker.run_once(dry_settings) is True

    check = worker_session_factory()
    try:
        row = check.get(Analysis, analysis_id)
        assert row is not None
        assert row.status == "done"
        assert row.progress == 100
        assert crawl_calls == []
        responses = (
            check.execute(select(Response).where(Response.analysis_id == analysis_id))
            .scalars()
            .all()
        )
        assert len(responses) == settings.prompt_count
    finally:
        check.close()


def test_guided_end_to_end_profile_pause_then_measure(
    client, db_session, signed_in, session_factory, monkeypatch, settings
):
    import app.worker as worker

    monkeypatch.setattr(worker, "SessionLocal", session_factory)
    monkeypatch.setattr(
        discovery,
        "discover_detailed",
        lambda url: discovery.CrawlResult(text="Acme builds warehouse robots and tools."),
    )

    user, org = signed_in()
    resp = client.post(
        "/api/v1/analyses",
        json={"url": "https://acme.test", "mode": "guided"},
    )
    assert resp.status_code == 202
    analysis_id = uuid.UUID(resp.json()["id"])

    dry_settings = Settings(dry_run=True)
    assert worker.run_once(dry_settings) is True

    db_session.expire_all()
    paused = db_session.get(Analysis, analysis_id)
    assert paused is not None
    assert paused.status == STATUS_AWAITING_REVIEW
    assert paused.progress == 45

    measure = client.post(EXECUTE_URL.format(id=analysis_id))
    assert measure.status_code == 202
    assert measure.json()["status"] == "queued"

    assert worker.run_once(dry_settings) is True

    db_session.expire_all()
    done = db_session.get(Analysis, analysis_id)
    assert done is not None
    assert done.status == "done"
    assert done.progress == 100
    responses = (
        db_session.execute(select(Response).where(Response.analysis_id == analysis_id))
        .scalars()
        .all()
    )
    assert len(responses) == settings.prompt_count


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
