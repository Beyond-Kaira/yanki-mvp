from __future__ import annotations

import pytest
from sqlalchemy import select

from app.pipeline.errors import PipelineError
from app.providers.base import ProviderResult


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

    # Responses: one per prompt per panel engine (4 engines in DRY_RUN).
    responses = db_session.execute(
        select(models.Response).where(models.Response.analysis_id == analysis.id)
    ).scalars().all()
    assert len(responses) == settings.prompt_count * 4
    assert result.total_responses == len(responses)

    # Footprint recorded on every response; score is consistent with the counts.
    assert all(response.footprint is not None for response in responses)
    hits = sum(1 for response in responses if response.footprint)
    assert result.footprint_count == hits
    assert result.geo_score == (hits / len(responses))
    assert 0.0 <= result.geo_score <= 1.0


class _CannedKycProvider:
    """Returns one fixed KYC payload for every call."""

    name = "canned"
    model = "canned"

    def __init__(self, payload: str) -> None:
        self._payload = payload

    def generate(self, prompt: str) -> ProviderResult:
        return ProviderResult(text=self._payload, model=self.model, cost_usd=0.0)


@pytest.mark.parametrize(
    "payload",
    [
        '{"company": "", "keywords": ["robots"]}',  # nothing for footprint to match
        '{"company": "Acme"}',  # no topic signal -> questions about "solutions"
    ],
)
def test_useless_profile_never_reaches_the_paid_fan_out(
    db_session, models, settings, monkeypatch, payload
):
    from app.pipeline import discovery, runner
    from app.pipeline import execute as execute_step
    from app.providers import registry

    monkeypatch.setattr(discovery, "discover", lambda url: "Some site text.")
    monkeypatch.setattr(
        registry, "get_analysis_provider", lambda _settings: _CannedKycProvider(payload)
    )
    calls: list[object] = []
    monkeypatch.setattr(
        execute_step, "run_execute", lambda *args, **kwargs: calls.append(args)
    )

    analysis = models.Analysis(url="https://example.com", status="running")
    db_session.add(analysis)
    db_session.flush()

    with pytest.raises(PipelineError):
        runner.run_pipeline(db_session, analysis.id, settings)

    # The point of the gate: execute (up to max_responses_per_job paid calls)
    # never started.
    assert calls == []
    # ...and the offending profile is still on the row, so it can be inspected.
    assert analysis.kyc is not None


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


# --------------------------------------------------------------------------
# SERP visibility (ADR-28) — runs inside the footprint step
# --------------------------------------------------------------------------


def _serp_checks(db_session, models, analysis):
    return (
        db_session.execute(
            select(models.SerpCheck).where(models.SerpCheck.analysis_id == analysis.id)
        )
        .scalars()
        .all()
    )


def test_serp_is_dark_unless_switched_on(db_session, models, settings, monkeypatch):
    """Off by default everywhere: every serp column stays NULL, no rows written.

    NULL is the honest record of "we did not measure", and it is what every row
    written before this feature existed already says.
    """
    from app.pipeline import discovery, runner

    monkeypatch.setattr(
        discovery, "discover", lambda url: "Acme builds warehouse robots and tools."
    )

    analysis = models.Analysis(url="https://example.com", status="running")
    db_session.add(analysis)
    db_session.flush()

    result = runner.run_pipeline(db_session, analysis.id, settings)

    assert result.serp_status is None
    assert result.serp_score is None
    assert result.serp_source is None
    assert result.serp_hit_count is None
    assert result.serp_query_count is None
    assert _serp_checks(db_session, models, analysis) == []


def test_serp_runs_in_the_footprint_step_without_touching_the_progress_contract(
    db_session, models, settings, monkeypatch
):
    from app.pipeline import discovery, runner

    monkeypatch.setattr(
        discovery, "discover", lambda url: "Acme builds warehouse robots and tools."
    )
    settings.serp_enabled = True  # DRY_RUN -> the deterministic mock source
    settings.serp_query_count = 4

    analysis = models.Analysis(url="https://example.com", status="running")
    db_session.add(analysis)
    db_session.flush()

    result = runner.run_pipeline(db_session, analysis.id, settings)

    # The locked step contract is untouched: no seventh step, same terminal state.
    assert result.status == "done"
    assert result.progress == 100
    assert result.current_step is None

    assert result.serp_status == "ok"
    assert result.serp_source == "mock"
    assert result.serp_query_count == 4
    assert result.serp_score == result.serp_hit_count / result.serp_query_count
    assert 0.0 <= result.serp_score <= 1.0

    checks = _serp_checks(db_session, models, analysis)
    assert len(checks) == 4
    assert all(check.query for check in checks)
    assert sum(1 for check in checks if check.hit) == result.serp_hit_count


def test_a_serp_outage_costs_the_number_and_not_the_job(
    db_session, models, settings, monkeypatch
):
    """The fail-open guarantee: SERP cannot fail a run that already cost money."""
    from app.pipeline import discovery, runner
    from app.serp.base import SerpUnavailable
    from app.serp.mock import MockSerpSource

    monkeypatch.setattr(
        discovery, "discover", lambda url: "Acme builds warehouse robots and tools."
    )

    def _down(self, query):
        raise SerpUnavailable("instance is down")

    monkeypatch.setattr(MockSerpSource, "search", _down)
    settings.serp_enabled = True
    settings.serp_query_count = 3

    analysis = models.Analysis(url="https://example.com", status="running")
    db_session.add(analysis)
    db_session.flush()

    result = runner.run_pipeline(db_session, analysis.id, settings)

    assert result.status == "done"
    assert result.geo_score is not None
    assert result.serp_status == "unavailable"
    assert result.serp_score is None


def test_a_rerun_replaces_serp_checks_rather_than_accumulating_them(
    db_session, models, settings, monkeypatch
):
    from app.pipeline import discovery, runner

    monkeypatch.setattr(
        discovery, "discover", lambda url: "Acme builds warehouse robots and tools."
    )
    settings.serp_enabled = True
    settings.serp_query_count = 3

    analysis = models.Analysis(url="https://example.com", status="running")
    db_session.add(analysis)
    db_session.flush()

    first = runner.run_pipeline(db_session, analysis.id, settings)
    second = runner.run_pipeline(db_session, analysis.id, settings)

    assert len(_serp_checks(db_session, models, analysis)) == 3
    assert second.serp_query_count == first.serp_query_count
    assert second.serp_hit_count == first.serp_hit_count
