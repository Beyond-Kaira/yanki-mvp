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

Two flavours share these six steps (P5.2). An MVP crawl analysis
(``kind`` NULL or ``'mvp'``) starts step 1 with an HTTP crawl of ``url`` and
templates a ``PROMPT_COUNT`` prompt set in step 3. A checker analysis
(``kind='checker'``) has a synthetic ``checker://`` url with no crawl target, so
step 1 seeds KYC from the submitted brand + category with **no** HTTP, and step
3 uses the fixed, versioned ``checker_prompts`` set. The progress mapping,
``current_step`` values, and steps 2 and 4-6 are identical for both — only the
discovery source and the prompt generator branch on ``kind``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select

from app.db.models import Analysis, Prompt, Response
from app.pipeline import checker_prompts, discovery
from app.pipeline import execute as execute_step
from app.pipeline import footprint as footprint_step
from app.pipeline import kyc as kyc_step
from app.pipeline import prompts as prompts_step
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
    analysis.claimed_at = _now()  # heartbeat
    # Commit so each step's output (and progress) survives a later-step failure:
    # the worker rolls back only the in-flight step's uncommitted work (FR-7).
    session.commit()


def _complete_step(session, analysis: Analysis, progress: int) -> None:
    analysis.progress = progress
    analysis.claimed_at = _now()  # heartbeat between steps
    session.commit()


def run_pipeline(session, analysis_id, settings) -> Analysis:
    analysis = session.execute(
        select(Analysis).where(Analysis.id == analysis_id)
    ).scalar_one()

    # Idempotency (NFR-3): a stale-claim re-run restarts from step 1 and only
    # ever appends prompts/responses, so clear any partial rows a prior crashed
    # attempt committed — otherwise they accumulate and double total_responses /
    # footprint_count. Responses first (they reference prompts).
    session.execute(delete(Response).where(Response.analysis_id == analysis.id))
    session.execute(delete(Prompt).where(Prompt.analysis_id == analysis.id))
    session.commit()

    is_checker = analysis.kind == "checker"

    # 1. discovery
    _start_step(session, analysis, "discovery")
    if is_checker:
        # A checker row has no crawl target (synthetic ``checker://`` url), so
        # seed KYC from the submitted brand + category instead of an HTTP crawl.
        # ``current_step``/``progress`` stay exactly as the MVP path sets them,
        # so the locked StepProgress contract is untouched.
        text = f"Brand: {analysis.brand}. Category: {analysis.category}."
    else:
        text = discovery.discover(analysis.url)
    _complete_step(session, analysis, _DISCOVERY_DONE)

    # 2. kyc
    _start_step(session, analysis, "kyc")
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
    _start_step(session, analysis, "prompts")
    if is_checker:
        # Fixed, versioned 12-prompt set (English wired; Turkish in P5.8). An
        # unwired lang falls back to English inside ``generate`` so a legal
        # submit never fails the job.
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

    # 4. execute
    _start_step(session, analysis, "execute")
    execute_step.run_execute(
        session, analysis.id, prompt_rows, registry.get_panel(settings), settings
    )
    _complete_step(session, analysis, _EXECUTE_DONE)

    # 5. footprint
    _start_step(session, analysis, "footprint")
    responses = (
        session.execute(select(Response).where(Response.analysis_id == analysis.id))
        .scalars()
        .all()
    )
    footprint_count = 0
    for response in responses:
        hit, snippet = footprint_step.detect(response.raw_text, kyc)
        response.footprint = hit
        response.matched_snippet = snippet
        if hit:
            footprint_count += 1
    session.flush()
    _complete_step(session, analysis, _FOOTPRINT_DONE)

    # 6. scoring
    _start_step(session, analysis, "scoring")
    total = len(responses)
    analysis.footprint_count = footprint_count
    analysis.total_responses = total
    analysis.geo_score = scoring_step.geo_score(footprint_count, total)
    analysis.status = "done"
    analysis.current_step = None
    analysis.progress = _SCORING_DONE
    analysis.claimed_at = _now()
    session.commit()
    return analysis
