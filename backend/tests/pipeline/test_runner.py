from __future__ import annotations

import pytest
from sqlalchemy import select

from app.pipeline.errors import PipelineError
from app.providers.base import ProviderResult
from app.providers.registry import get_openrouter_models
from tests.pipeline.conftest import geo_response_count


def _stub_discovery(monkeypatch, text: str = "Acme builds warehouse robots and tools.") -> None:
    from app.pipeline import discovery

    monkeypatch.setattr(
        discovery,
        "discover_detailed",
        lambda url: discovery.CrawlResult(text=text, pages=()),
    )


def test_run_pipeline_walks_all_steps_and_scores(db_session, models, settings, monkeypatch):
    from app.pipeline import runner

    _stub_discovery(monkeypatch)

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
    prompts = (
        db_session.execute(select(models.Prompt).where(models.Prompt.analysis_id == analysis.id))
        .scalars()
        .all()
    )
    assert len(prompts) == settings.prompt_count

    # Responses: one row per prompt × model slug.
    expected_responses = geo_response_count(settings, settings.prompt_count)
    responses = (
        db_session.execute(
            select(models.Response).where(models.Response.analysis_id == analysis.id)
        )
        .scalars()
        .all()
    )
    assert len(responses) == expected_responses
    assert result.total_responses == len(responses)
    assert all(response.llm_provider == "openrouter" for response in responses)
    assert len({response.model for response in responses}) == len(get_openrouter_models(settings))
    assert all(isinstance(response.audit, dict) for response in responses)
    assert result.geo_run is not None
    assert result.geo_run["mode"] == "measured"
    assert result.geo_run["llm"]["provider"] == "openrouter"
    assert result.geo_run["llm"]["models"] == get_openrouter_models(settings)

    geo_rows = (
        db_session.execute(
            select(models.GeoRecord).where(models.GeoRecord.analysis_id == analysis.id)
        )
        .scalars()
        .all()
    )
    assert len(geo_rows) == expected_responses
    assert result.citation_summary is not None
    assert result.citation_summary["record_count"] == expected_responses

    # Footprint recorded on every response; composite score in 0–100.
    assert all(response.footprint is not None for response in responses)
    hits = sum(1 for response in responses if response.footprint)
    assert result.footprint_count == hits
    assert result.geo_score is not None
    assert 0.0 <= result.geo_score <= 100.0


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
    from app.pipeline import execute_measured, runner
    from app.providers import registry

    _stub_discovery(monkeypatch, text="Some site text.")
    monkeypatch.setattr(
        registry, "get_analysis_provider", lambda _settings: _CannedKycProvider(payload)
    )
    calls: list[object] = []
    monkeypatch.setattr(
        execute_measured,
        "run_measured_execute",
        lambda *args, **kwargs: calls.append(args) or [],
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


def test_rerun_replaces_rows_and_does_not_double_counts(db_session, models, settings, monkeypatch):
    # NFR-3: a stale-claim re-run must replace prior partial rows, not accumulate
    # them (else total_responses / footprint_count double).
    from app.pipeline import runner

    _stub_discovery(monkeypatch)

    analysis = models.Analysis(url="https://example.com", status="running")
    db_session.add(analysis)
    db_session.flush()

    first = runner.run_pipeline(db_session, analysis.id, settings)
    first_total = first.total_responses
    first_footprints = first.footprint_count

    # Re-run the same analysis (as the stale-claim reaper would).
    second = runner.run_pipeline(db_session, analysis.id, settings)

    prompts = (
        db_session.execute(select(models.Prompt).where(models.Prompt.analysis_id == analysis.id))
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
    from app.pipeline import runner

    _stub_discovery(monkeypatch)

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
    from app.pipeline import runner

    _stub_discovery(monkeypatch)
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


def test_a_serp_outage_costs_the_number_and_not_the_job(db_session, models, settings, monkeypatch):
    """The fail-open guarantee: SERP cannot fail a run that already cost money."""
    from app.pipeline import runner
    from app.serp.base import SerpUnavailable
    from app.serp.mock import MockSerpSource

    _stub_discovery(monkeypatch)

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
    from app.pipeline import runner

    _stub_discovery(monkeypatch)
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


def test_a_rerun_with_serp_switched_off_leaves_no_score_without_evidence(
    db_session, models, settings, monkeypatch
):
    """A summary and the evidence under it are cleared together, or not at all.

    The reachable path: a run measures SERP, the operator turns the feature off,
    and the stale-claim reaper re-runs the job. The re-run drops the serp_checks
    rows; if the summary columns survived that, the API would serve a score with
    an empty evidence table behind it — a number with no working shown, which is
    the one thing this feature exists not to produce.
    """
    from app.pipeline import runner

    _stub_discovery(monkeypatch)
    settings.serp_enabled = True
    settings.serp_query_count = 3

    analysis = models.Analysis(url="https://example.com", status="running")
    db_session.add(analysis)
    db_session.flush()

    measured = runner.run_pipeline(db_session, analysis.id, settings)
    assert measured.serp_score is not None
    assert _serp_checks(db_session, models, analysis)

    settings.serp_enabled = False
    rerun = runner.run_pipeline(db_session, analysis.id, settings)

    assert _serp_checks(db_session, models, analysis) == []
    assert rerun.serp_score is None
    assert rerun.serp_status is None
    assert rerun.serp_source is None
    assert rerun.serp_hit_count is None
    assert rerun.serp_query_count is None


# --------------------------------------------------------------------------
# SEO audit (ADR-31) — runs inside the discovery step
# --------------------------------------------------------------------------


def _seo_checks(db_session, models, analysis):
    return (
        db_session.execute(
            select(models.SeoCheck).where(models.SeoCheck.analysis_id == analysis.id)
        )
        .scalars()
        .all()
    )


def test_the_audit_runs_in_the_discovery_step_and_stores_its_evidence(
    db_session, models, settings, monkeypatch
):
    from app.pipeline import discovery, runner, seo_audit
    from app.pipeline.discovery import CrawlResult, PageAudit
    from app.pipeline.robots import RobotsReport

    home = PageAudit(
        url="https://example.com/",
        final_url="https://example.com/",
        status_code=200,
        is_home=True,
        title="Acme",
        h1_count=1,
        lang="en",
        server_text_chars=5000,
    )
    monkeypatch.setattr(
        discovery,
        "discover_detailed",
        lambda url: CrawlResult(text="Acme builds warehouse robots.", pages=(home,)),
    )
    # No network for robots.txt either: the audit's only fetch is stubbed out.
    monkeypatch.setattr(
        seo_audit.robots, "fetch", lambda client, url: RobotsReport(measured=True, absent=True)
    )

    analysis = models.Analysis(url="https://example.com", status="running")
    db_session.add(analysis)
    db_session.flush()

    result = runner.run_pipeline(db_session, analysis.id, settings)

    # The locked step contract is untouched — no seventh step.
    assert result.status == "done"
    assert result.progress == 100
    assert result.current_step is None

    assert result.seo_status == "ok"
    assert result.seo_grade
    assert 0.0 <= result.seo_score <= 100.0
    checks = _seo_checks(db_session, models, analysis)
    assert checks
    assert all(c.check_id and c.title and c.severity and c.status for c in checks)


def test_an_audit_failure_costs_the_grade_and_not_the_run(
    db_session, models, settings, monkeypatch
):
    """Fail-open, like the SERP pass: the crawl has already been paid for."""
    from app.pipeline import discovery, runner, seo_audit
    from app.pipeline.discovery import CrawlResult

    monkeypatch.setattr(
        discovery,
        "discover_detailed",
        lambda url: CrawlResult(text="Acme builds warehouse robots.", pages=()),
    )

    def _boom(client, url):
        raise RuntimeError("robots fetch exploded")

    monkeypatch.setattr(seo_audit.robots, "fetch", _boom)

    analysis = models.Analysis(url="https://example.com", status="running")
    db_session.add(analysis)
    db_session.flush()

    result = runner.run_pipeline(db_session, analysis.id, settings)

    assert result.status == "done"
    assert result.geo_score is not None
    assert result.seo_status == "error"
    assert result.seo_grade is None


def test_a_checker_run_has_no_site_to_audit(db_session, models, settings, monkeypatch):
    from app.pipeline import runner

    analysis = models.Analysis(
        url="checker://acme/robots",
        status="running",
        kind="checker",
        brand="acme",
        category="warehouse robots",
        lang="en",
    )
    db_session.add(analysis)
    db_session.flush()

    result = runner.run_pipeline(db_session, analysis.id, settings)

    assert result.seo_status is None
    assert result.seo_grade is None
    assert _seo_checks(db_session, models, analysis) == []
