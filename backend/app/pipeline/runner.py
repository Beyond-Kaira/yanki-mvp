"""Orchestrate the six pipeline steps for one analysis.

``run_pipeline`` walks discovery -> kyc -> prompts -> measured execute ->
reliability/footprint sync -> composite scoring (+ interventions placeholder),
advancing ``current_step`` and ``progress`` and heartbeating ``claimed_at``
after each step.

Two flavours share these six steps. An MVP crawl analysis (``kind`` NULL or
``'mvp'``) starts step 1 with an HTTP crawl of ``url`` and templates a
``PROMPT_COUNT`` prompt set in step 3. A checker analysis (``kind='checker'``)
seeds KYC from brand + category with no HTTP, and uses ``checker_prompts``.
Steps 4–6 are the measured GEO path for both.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select

from app.db.models import Analysis, Prompt, Response
from app.pipeline import checker_prompts, discovery
from app.pipeline import execute_measured as execute_step
from app.pipeline import interventions as interventions_step
from app.pipeline import kyc as kyc_step
from app.pipeline import prompts as prompts_step
from app.pipeline import reliability as reliability_step
from app.pipeline import scoring as scoring_step
from app.providers import registry

# progress % set when each step COMPLETES (see the master SPEC).
_DISCOVERY_DONE = 15
_KYC_DONE = 30
_PROMPTS_DONE = 45
_EXECUTE_DONE = 80
_FOOTPRINT_DONE = 90
_SCORING_DONE = 100


def _now():
    return datetime.now(UTC)


def _start_step(session, analysis: Analysis, step: str) -> None:
    analysis.current_step = step
    analysis.claimed_at = _now()
    session.commit()


def _complete_step(session, analysis: Analysis, progress: int) -> None:
    analysis.progress = progress
    analysis.claimed_at = _now()
    session.commit()


def run_pipeline(session, analysis_id, settings) -> Analysis:
    analysis = session.execute(
        select(Analysis).where(Analysis.id == analysis_id)
    ).scalar_one()

    session.execute(delete(Response).where(Response.analysis_id == analysis.id))
    session.execute(delete(Prompt).where(Prompt.analysis_id == analysis.id))
    session.commit()

    is_checker = analysis.kind == "checker"

    # 1. discovery
    _start_step(session, analysis, "discovery")
    if is_checker:
        text = f"Brand: {analysis.brand}. Category: {analysis.category}."
    else:
        text = discovery.discover(analysis.url)
    _complete_step(session, analysis, _DISCOVERY_DONE)

    # 2. kyc
    _start_step(session, analysis, "kyc")
    kyc = kyc_step.generate_kyc(
        text, analysis.url, registry.get_analysis_provider(settings)
    )
    analysis.kyc = kyc.model_dump()
    _complete_step(session, analysis, _KYC_DONE)

    # 3. prompts
    _start_step(session, analysis, "prompts")
    if is_checker:
        specs = checker_prompts.generate(kyc, analysis.lang or "en")
    else:
        specs = prompts_step.generate_prompts(
            kyc, getattr(settings, "prompt_count", 10)
        )
    prompt_rows = []
    for spec in specs:
        row = Prompt(analysis_id=analysis.id, text=spec.text, category=spec.category)
        session.add(row)
        prompt_rows.append(row)
    session.flush()
    _complete_step(session, analysis, _PROMPTS_DONE)

    # 4. measured execute (Tavily + OpenRouter, or mocks under DRY_RUN)
    _start_step(session, analysis, "execute")
    responses = execute_step.run_measured_execute(
        session, analysis, prompt_rows, settings
    )
    _complete_step(session, analysis, _EXECUTE_DONE)

    # 5. reliability over measured audits (+ footprint recount)
    _start_step(session, analysis, "footprint")
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
    session.flush()
    _complete_step(session, analysis, _FOOTPRINT_DONE)

    # 6. interventions + composite GEO score (gaps excluded from score)
    _start_step(session, analysis, "scoring")
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
    analysis.status = "done"
    analysis.current_step = None
    analysis.progress = _SCORING_DONE
    analysis.claimed_at = _now()
    session.commit()
    return analysis
