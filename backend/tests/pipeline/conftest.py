"""Fixtures for the pipeline unit tests.

Pure-function tests (scoring, footprint, prompts, kyc parsing, mock, registry,
discovery) need nothing from the database and always run. The DB-backed tests
(execute, runner) use ``db_session`` / ``models``, which import the spine
agent's ``app.db`` via ``pytest.importorskip`` so they skip cleanly if that
module is not present yet.
"""

from __future__ import annotations

import pytest

from app.config import Settings
from app.pipeline.kyc import KYC
from app.providers.registry import get_openrouter_models


def geo_response_count(settings, prompt_count: int) -> int:
    """Expected ``responses`` rows after execute (prompts × configured models)."""

    return prompt_count * len(get_openrouter_models(settings))


@pytest.fixture
def settings(tmp_path_factory):
    """Settings tuned for pipeline tests (DRY_RUN, default multi-LLM list).

    ``worker_heartbeat_path`` points at a temp file because `run_pipeline` beats
    at every step (ADR-47) and the real default, `/var/run/yanki/`, is a volume
    that exists only in a container.
    """

    return Settings(
        dry_run=True,
        panel_engines="anthropic,openai,gemini,perplexity",
        prompt_count=4,
        max_responses_per_job=60,
        anthropic_api_key="",
        openai_api_key="",
        worker_heartbeat_path=str(tmp_path_factory.mktemp("heartbeat") / "worker.heartbeat"),
    )


@pytest.fixture
def sample_kyc() -> KYC:
    return KYC(
        company="Acme Robotics",
        description="Industrial robots for warehouses.",
        industry="Robotics",
        aliases=["Acme Robotics", "Acme", "acmerobotics"],
        products=["ArmBot", "PalletMover"],
        keywords=["automation", "warehouse"],
        locations=["Berlin"],
        competitors=["Globex", "Initech"],
    )


@pytest.fixture
def models():
    """The spine agent's SQLAlchemy models, or skip if not available yet."""
    return pytest.importorskip("app.db.models")


@pytest.fixture
def db_session():
    """An in-memory SQLite session mirroring the app's SessionLocal.

    A ``StaticPool`` shares one connection so committed rows stay visible, and
    ``expire_on_commit=False`` matches ``app.db.session.SessionLocal`` (the
    runner commits after each step).
    """
    base = pytest.importorskip("app.db.base")
    pytest.importorskip("app.db.models")  # registers tables on the metadata
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    base.Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


@pytest.fixture
def seeded_analysis(db_session, models):
    """An ``analyses`` row plus a couple of ``prompts`` rows to execute against."""
    analysis = models.Analysis(url="https://example.com", status="running")
    db_session.add(analysis)
    db_session.flush()
    prompts = [
        models.Prompt(analysis_id=analysis.id, text=f"Question {i}?", category="recommendation")
        for i in range(3)
    ]
    db_session.add_all(prompts)
    db_session.flush()
    return analysis, prompts
