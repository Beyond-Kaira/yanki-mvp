"""Worker terminal-status alert tests (P5.13).

On a terminal status (``done``/``failed``) the worker fires a best-effort
operator alert. The run is already recorded in ``analyses``; the email is only
telemetry, so a raising or disabled alert must NEVER change the pipeline result.
Runs against an in-memory SQLite DB, exactly like test_worker.py.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
import respx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.worker as worker
from app.config import Settings
from app.db.base import Base
from app.db.models import Analysis
from app.services.emailer import RESEND_ENDPOINT


@pytest.fixture
def worker_session_factory(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(worker, "SessionLocal", factory)
    yield factory
    engine.dispose()


def _seed_queued(factory) -> uuid.UUID:
    session = factory()
    analysis = Analysis(url="https://example.com", status="queued")
    session.add(analysis)
    session.commit()
    analysis_id = analysis.id
    session.close()
    return analysis_id


def _no_network_discovery(monkeypatch):
    from app.pipeline import discovery

    monkeypatch.setattr(
        discovery,
        "discover_detailed",
        lambda url: discovery.CrawlResult(text="Acme builds robots."),
    )


def test_alert_fires_on_done_terminal_status(worker_session_factory, monkeypatch):
    _no_network_discovery(monkeypatch)
    seen: list[tuple[str, str]] = []
    monkeypatch.setattr(worker, "send_run_alert", lambda a, s: seen.append((a.status, str(a.id))))
    analysis_id = _seed_queued(worker_session_factory)

    assert worker.run_once(Settings(dry_run=True)) is True
    assert seen == [("done", str(analysis_id))]


def test_alert_fires_on_failed_terminal_status(worker_session_factory, monkeypatch):
    from app.pipeline import scoring
    from app.pipeline.errors import PipelineError

    _no_network_discovery(monkeypatch)

    def _boom(records, *, reliability_score=None):
        raise PipelineError("scoring exploded")

    monkeypatch.setattr(scoring, "geo_score", _boom)
    seen: list[str] = []
    monkeypatch.setattr(worker, "send_run_alert", lambda a, s: seen.append(a.status))
    _seed_queued(worker_session_factory)

    assert worker.run_once(Settings(dry_run=True)) is True
    assert seen == ["failed"]


def test_raising_alert_never_changes_the_pipeline_result(worker_session_factory, monkeypatch):
    _no_network_discovery(monkeypatch)

    def _raise(analysis, settings):
        raise RuntimeError("resend is down")

    monkeypatch.setattr(worker, "send_run_alert", _raise)
    analysis_id = _seed_queued(worker_session_factory)

    # The alert blows up, but the run still completes as done — the email is not
    # the record, so its failure is swallowed.
    assert worker.run_once(Settings(dry_run=True)) is True
    check = worker_session_factory()
    try:
        row = check.get(Analysis, analysis_id)
        assert row.status == "done"
    finally:
        check.close()


@respx.mock
def test_alert_is_silent_when_emails_disabled(worker_session_factory, monkeypatch):
    # Real send_run_alert + send_email (not monkeypatched). notify_email is set so
    # we pass the early return, but emails are disabled, so no HTTP call is made.
    route = respx.post(RESEND_ENDPOINT).mock(return_value=httpx.Response(200))
    _no_network_discovery(monkeypatch)
    _seed_queued(worker_session_factory)

    settings = Settings(dry_run=True, emails_enabled=False, notify_email="ops@yanki.test")
    assert worker.run_once(settings) is True
    assert not route.called
