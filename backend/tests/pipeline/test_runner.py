from __future__ import annotations

from sqlalchemy import select


def test_run_pipeline_walks_all_steps_and_scores(db_session, models, settings, monkeypatch):
    from app.pipeline import discovery, runner

    # Avoid real network: hand discovery a canned page.
    monkeypatch.setattr(
        discovery, "discover", lambda url: "Acme builds warehouse robots and tools."
    )

    analysis = models.Analysis(url="https://example.com", status="running")
    db_session.add(analysis)
    db_session.flush()

    result = runner.run_pipeline(db_session, analysis.id, settings)

    # Final status + progress + heartbeat.
    assert result.status == "done"
    assert result.progress == 100
    assert result.current_step is None
    assert result.claimed_at is not None

    # KYC persisted as JSON with a company name.
    assert result.kyc is not None
    assert result.kyc["company"]

    # Prompts persisted (PROMPT_COUNT of them).
    prompts = db_session.execute(
        select(models.Prompt).where(models.Prompt.analysis_id == analysis.id)
    ).scalars().all()
    assert len(prompts) == settings.prompt_count

    # Responses: one measured audit per prompt.
    responses = db_session.execute(
        select(models.Response).where(models.Response.analysis_id == analysis.id)
    ).scalars().all()
    assert len(responses) == settings.prompt_count
    assert result.total_responses == len(responses)
    assert all(response.engine == "measured" for response in responses)
    assert all(isinstance(response.audit, dict) for response in responses)

    # Footprint recorded on every response; composite score in 0–100.
    assert all(response.footprint is not None for response in responses)
    hits = sum(1 for response in responses if response.footprint)
    assert result.footprint_count == hits
    assert result.geo_score is not None
    assert 0.0 <= result.geo_score <= 100.0


def test_rerun_replaces_rows_and_does_not_double_counts(
    db_session, models, settings, monkeypatch
):
    # NFR-3: a stale-claim re-run must replace prior partial rows, not accumulate
    # them (else total_responses / footprint_count double).
    from app.pipeline import discovery, runner

    monkeypatch.setattr(
        discovery, "discover", lambda url: "Acme builds warehouse robots and tools."
    )

    analysis = models.Analysis(url="https://example.com", status="running")
    db_session.add(analysis)
    db_session.flush()

    first = runner.run_pipeline(db_session, analysis.id, settings)
    first_total = first.total_responses
    first_footprints = first.footprint_count

    # Re-run the same analysis (as the stale-claim reaper would).
    second = runner.run_pipeline(db_session, analysis.id, settings)

    prompts = db_session.execute(
        select(models.Prompt).where(models.Prompt.analysis_id == analysis.id)
    ).scalars().all()
    responses = db_session.execute(
        select(models.Response).where(models.Response.analysis_id == analysis.id)
    ).scalars().all()

    assert len(prompts) == settings.prompt_count
    assert len(responses) == first_total
    assert second.total_responses == first_total
    assert second.footprint_count == first_footprints
