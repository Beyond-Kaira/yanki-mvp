"""End-to-end: a kind='checker' analysis walks all six steps with NO crawl.

Runs under DRY_RUN (the pipeline ``settings`` fixture), so every provider is a
deterministic mock and the whole run is free and reproducible. The discovery
step is monkeypatched to *raise* so the test proves the checker branch never
calls it — the seed KYC comes from the brand + category, not an HTTP crawl.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select


def _make_checker(db_session, models):
    analysis = models.Analysis(
        url="checker://nike/running shoes",
        status="running",
        kind="checker",
        brand="nike",
        category="running shoes",
        lang="en",
    )
    db_session.add(analysis)
    db_session.flush()
    return analysis


def _forbid_crawl(monkeypatch):
    from app.pipeline import discovery

    def _boom(url):  # pragma: no cover - only runs if the branch is wrong
        raise AssertionError(f"discovery.discover must not run for a checker row (url={url})")

    monkeypatch.setattr(discovery, "discover", _boom)


def test_checker_pipeline_walks_all_steps_without_crawl(
    db_session, models, settings, monkeypatch
):
    from app.pipeline import runner

    _forbid_crawl(monkeypatch)
    analysis = _make_checker(db_session, models)

    result = runner.run_pipeline(db_session, analysis.id, settings)

    # Final status + locked progress mapping + heartbeat.
    assert result.status == "done"
    assert result.progress == 100
    assert result.current_step is None
    assert result.claimed_at is not None

    # KYC persisted (the seed ran through the mock KYC provider).
    assert result.kyc is not None
    assert result.kyc["company"]

    # Exactly 12 prompts (the fixed checker set), not settings.prompt_count.
    prompts = (
        db_session.execute(
            select(models.Prompt).where(models.Prompt.analysis_id == analysis.id)
        )
        .scalars()
        .all()
    )
    assert len(prompts) == 12

    # 12 measured responses = 12 prompts × 1 measured engine.
    responses = (
        db_session.execute(
            select(models.Response).where(models.Response.analysis_id == analysis.id)
        )
        .scalars()
        .all()
    )
    assert len(responses) == 12
    assert result.total_responses == 12
    assert all(r.engine == "measured" for r in responses)
    assert all(isinstance(r.audit, dict) for r in responses)

    # Footprint recorded on every response; composite GEO in 0–100.
    assert all(r.footprint is not None for r in responses)
    hits = sum(1 for r in responses if r.footprint)
    assert result.footprint_count == hits
    assert hits > 0
    assert result.geo_score is not None
    assert 0.0 < result.geo_score <= 100.0


def test_checker_rerun_is_idempotent(db_session, models, settings, monkeypatch):
    # A stale-claim re-run restarts from step 1 and must replace prior rows, not
    # accumulate them (else prompts/responses double). NFR-3.
    from app.pipeline import runner

    _forbid_crawl(monkeypatch)
    analysis = _make_checker(db_session, models)

    first = runner.run_pipeline(db_session, analysis.id, settings)
    second = runner.run_pipeline(db_session, analysis.id, settings)

    prompts = (
        db_session.execute(
            select(models.Prompt).where(models.Prompt.analysis_id == analysis.id)
        )
        .scalars()
        .all()
    )
    responses = (
        db_session.execute(
            select(models.Response).where(models.Response.analysis_id == analysis.id)
        )
        .scalars()
        .all()
    )
    assert len(prompts) == 12
    assert len(responses) == 12
    assert second.total_responses == first.total_responses == 12
    assert second.footprint_count == first.footprint_count
