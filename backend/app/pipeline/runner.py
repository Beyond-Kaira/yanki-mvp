"""Orchestrate the six pipeline steps for one analysis.

``run_pipeline`` walks discovery -> kyc -> prompts -> execute -> footprint ->
scoring, advancing ``current_step`` and ``progress`` and heartbeating
``claimed_at`` after each step, and persisting each step's output as it goes so
partial results stay queryable. On success it marks the analysis ``done``.
The worker owns claiming the job and turning any raised exception into a
``failed`` status.

Between steps 2 and 3 it gates on ``kyc.require_usable``: a profile with no
company or no topic signal can only produce a meaningless score, so the job stops
before ``execute`` spends up to ``max_responses_per_job`` paid calls on it.

Two flavours share these six steps. An MVP crawl analysis (``kind`` NULL or
``'mvp'``) starts step 1 with an HTTP crawl of ``url`` and templates a
``PROMPT_COUNT`` prompt set in step 3. A checker analysis (``kind='checker'``)
seeds KYC from brand + category with no HTTP, and uses ``checker_prompts``.
Steps 4–6 are the measured GEO path for both.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app import health
from app.db.models import Analysis, Prompt, Response
from app.pipeline import checker_prompts, discovery
from app.pipeline import execute_measured as execute_step
from app.pipeline import geo_records as geo_records_step
from app.pipeline import interventions as interventions_step
from app.pipeline import kyc as kyc_step
from app.pipeline import prompts as prompts_step
from app.pipeline import reliability as reliability_step
from app.pipeline import scoring as scoring_step
from app.pipeline import seo_audit as seo_step
from app.pipeline import serp_visibility as serp_step
from app.providers import registry
from app.serp import registry as serp_registry
from app.services.analyses import delete_analysis_children

# progress % set when each step COMPLETES (see the master SPEC).
_DISCOVERY_DONE = 15
_KYC_DONE = 30
_PROMPTS_DONE = 45
_EXECUTE_DONE = 80
_FOOTPRINT_DONE = 90
_SCORING_DONE = 100


def _now():
    return datetime.now(UTC)


def _start_step(session, analysis: Analysis, step: str, settings) -> None:
    analysis.current_step = step
    analysis.claimed_at = _now()
    # The same event, told to two audiences: `claimed_at` stops the stale-claim
    # reaper taking this job away, and the heartbeat file stops `/healthz` and
    # the compose healthcheck reporting a busy worker as a stopped one (ADR-47).
    # A step is the right granularity for both — it is the unit the pipeline
    # already treats as "still making progress".
    health.beat(settings)
    session.commit()


def _complete_step(session, analysis: Analysis, progress: int) -> None:
    analysis.progress = progress
    analysis.claimed_at = _now()
    session.commit()


def run_pipeline(session, analysis_id, settings) -> Analysis:
    analysis = session.execute(select(Analysis).where(Analysis.id == analysis_id)).scalar_one()

    delete_analysis_children(session, analysis.id)
    # The SERP summary is cleared with the evidence it summarises, not alongside
    # the code that writes it. Otherwise a re-run with SERP switched off since
    # the last attempt drops the ``serp_checks`` rows and keeps the old score —
    # a number with nothing under it, which is the exact thing this feature
    # exists not to produce (ADR-28). Only a completed pass writes them back.
    analysis.serp_score = None
    analysis.serp_hit_count = None
    analysis.serp_query_count = None
    analysis.serp_status = None
    analysis.serp_source = None
    analysis.seo_score = None
    analysis.seo_grade = None
    analysis.seo_status = None
    session.commit()

    is_checker = analysis.kind == "checker"

    # 1. discovery
    _start_step(session, analysis, "discovery", settings)
    if is_checker:
        text = f"Brand: {analysis.brand}. Category: {analysis.category}."
    else:
        crawl = discovery.discover_detailed(analysis.url)
        text = crawl.text
        # The SEO audit rides in this step (ADR-31): it is a second reading of
        # the crawl we just paid for, so it belongs where the crawl is and adds
        # no pipeline step. A checker row has no site to audit. ``run_audit``
        # never raises — an audit defect costs the run its grade and nothing
        # else — and the one extra fetch is robots.txt.
        seo = seo_step.run_audit(session, analysis, crawl)
        analysis.seo_status = seo.status
        analysis.seo_score = seo.score
        analysis.seo_grade = seo.grade
    _complete_step(session, analysis, _DISCOVERY_DONE)

    # 2. kyc
    _start_step(session, analysis, "kyc", settings)
    kyc = kyc_step.generate_kyc(
        text,
        analysis.url,
        registry.get_analysis_provider(settings),
        # Grounding checks the model's proper nouns against the crawl. A checker
        # row has no crawl — its "text" is the brand + category sentence composed
        # above — so verifying against it would delete every competitor the model
        # knows and degrade the run to the neutral fallbacks.
        verify_against_source=not is_checker,
    )
    analysis.kyc = kyc.model_dump()
    _complete_step(session, analysis, _KYC_DONE)

    # Refuse to fan out on input we already know is unusable. ``execute`` below
    # is the most expensive step in the pipeline (up to ``max_responses_per_job``
    # paid calls), and an empty company or a topic-free profile can only buy a
    # plausible-looking score that is quietly meaningless. Gating *after* the
    # commit above means the offending profile stays queryable on the failed row,
    # so an operator can see exactly what came back. A checker row contributes
    # its submitted category, which is real input the model may not have echoed.
    kyc_step.require_usable(kyc, known_topic=analysis.category if is_checker else "")

    # 3. prompts
    _start_step(session, analysis, "prompts", settings)
    if is_checker:
        specs = checker_prompts.generate(kyc, analysis.lang or "en")
    else:
        specs = prompts_step.generate_prompts(kyc, getattr(settings, "prompt_count", 10))
    prompt_rows = []
    for spec in specs:
        row = Prompt(analysis_id=analysis.id, text=spec.text, category=spec.category)
        session.add(row)
        prompt_rows.append(row)
    session.flush()
    _complete_step(session, analysis, _PROMPTS_DONE)

    # 4. measured execute (Tavily + OpenRouter, or mocks under DRY_RUN)
    _start_step(session, analysis, "execute", settings)
    responses = execute_step.run_measured_execute(session, analysis, prompt_rows, settings)
    _complete_step(session, analysis, _EXECUTE_DONE)

    # 5. reliability over measured audits (+ footprint recount)
    _start_step(session, analysis, "footprint", settings)
    if not responses:
        responses = (
            session.execute(select(Response).where(Response.analysis_id == analysis.id))
            .scalars()
            .all()
        )
    audit_records = [r.audit for r in responses if isinstance(r.audit, dict)]
    reliability_report = reliability_step.analyze_records(audit_records)
    analysis.reliability_score = reliability_report.get("reliability_score")
    footprint_count = sum(1 for response in responses if response.footprint)

    # SERP visibility rides in this step rather than a seventh one (ADR-28):
    # footprint is the step that asks where the brand actually appears, and this
    # asks it of search results instead of LLM answers. ``current_step`` and the
    # progress mapping are therefore unchanged. ``run_serp`` never raises — a
    # search instance having a bad day costs the run its SERP number and nothing
    # more — and a run with SERP switched off leaves every ``serp_*`` column
    # null, which says "not measured" rather than "measured zero".
    serp_source = serp_registry.get_serp_source(settings)
    if serp_source is not None:
        outcome = serp_step.run_serp(session, analysis, kyc, serp_source, settings)
        analysis.serp_status = outcome.status
        analysis.serp_source = outcome.source or None
        analysis.serp_hit_count = outcome.hits
        analysis.serp_query_count = outcome.queries
        analysis.serp_score = outcome.score

    session.flush()
    _complete_step(session, analysis, _FOOTPRINT_DONE)

    # 6. interventions + composite GEO score (gaps excluded from score)
    _start_step(session, analysis, "scoring", settings)
    intervention_report = interventions_step.analyze_records(audit_records)
    analysis.interventions = intervention_report.get("aggregated_interventions") or []
    total = len(responses)
    analysis.footprint_count = footprint_count
    analysis.total_responses = total
    if audit_records:
        analysis.geo_score = scoring_step.geo_score(
            audit_records,
            reliability_score=analysis.reliability_score,
        )
    else:
        analysis.geo_score = scoring_step.mention_rate(footprint_count, total) * 100.0
    analysis.citation_summary = geo_records_step.aggregate_citation_summary(audit_records)
    analysis.status = "done"
    analysis.current_step = None
    analysis.progress = _SCORING_DONE
    analysis.claimed_at = _now()
    session.commit()
    return analysis
