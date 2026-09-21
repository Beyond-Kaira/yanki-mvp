"""Standalone module run handlers — one job kind, no cross-module chaining (mod-6)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Analysis, BrandContext, ModuleRun, Prompt
from app.jobs.module_kinds import JOB_KIND_GEO_RUN, JOB_KIND_KYC_EXTRACT, JOB_KIND_SERP_RUN
from app.net_guard import is_public_url
from app.pipeline import kyc as kyc_step
from app.pipeline import serp_visibility as serp_step
from app.pipeline.runner import run_geo_only
from app.services.brand_contexts import extract_brand_context_profile
from app.serp import registry as serp_registry

logger = logging.getLogger("yanki.module_handlers")


class ModuleRunError(Exception):
    """Expected handler failure — surfaced as ``module_runs.error``."""


def _brand_url(context: BrandContext) -> str:
    if context.source_url:
        return context.source_url
    if context.domain:
        return f"https://{context.domain}/"
    return "https://unknown.test/"


def _load_brand_context(session: Session, run: ModuleRun) -> BrandContext:
    if run.brand_context_id is None:
        raise ModuleRunError("brand_context_id is required")
    context = session.get(BrandContext, run.brand_context_id)
    if context is None:
        raise ModuleRunError("brand context not found")
    if run.org_id is not None and context.org_id != run.org_id:
        raise ModuleRunError("brand context not found")
    return context


def _kyc_from_context(context: BrandContext) -> kyc_step.KYC:
    profile = context.profile or {"company": context.brand}
    return kyc_step.KYC.model_validate(profile)


def _shell_analysis(session: Session, run: ModuleRun, context: BrandContext, *, kind: str) -> Analysis:
    analysis = Analysis(
        url=_brand_url(context),
        kind=kind,
        status="running",
        org_id=run.org_id,
        created_by_user_id=run.created_by_user_id,
        brand_context_id=context.id,
        kyc=(context.profile or {"company": context.brand}),
        run_mode="quick",
        lang=context.locale or "en",
    )
    session.add(analysis)
    session.flush()
    run.linked_analysis_id = analysis.id
    session.flush()
    return analysis


def handle_kyc_extract(session: Session, run: ModuleRun, settings: Settings) -> dict[str, Any]:
    context = _load_brand_context(session, run)
    payload = run.payload or {}
    source_url = (payload.get("source_url") or context.source_url or "").strip()
    if not source_url:
        raise ModuleRunError("source_url is required")
    if not is_public_url(source_url):
        raise ModuleRunError("url is not allowed")

    run.current_step = "extract"
    run.progress = 10
    session.commit()

    context = extract_brand_context_profile(
        session,
        context=context,
        source_url=source_url,
        settings=settings,
    )
    run.progress = 100
    return {
        "brand_context_id": str(context.id),
        "brand": context.brand,
        "category": context.category,
    }


def handle_serp_run(session: Session, run: ModuleRun, settings: Settings) -> dict[str, Any]:
    context = _load_brand_context(session, run)
    kyc = _kyc_from_context(context)
    kyc_step.require_usable(kyc, known_topic=context.category or "")

    run.current_step = "serp"
    run.progress = 5
    session.commit()

    analysis = _shell_analysis(session, run, context, kind="serp_run")

    serp_source = serp_registry.get_serp_source(settings)
    if serp_source is None:
        analysis.status = "done"
        analysis.serp_status = serp_step.STATUS_UNAVAILABLE
        session.commit()
        return {
            "analysis_id": str(analysis.id),
            "serp_status": analysis.serp_status,
            "reason": "no serp source configured",
        }

    outcome = serp_step.run_serp(session, analysis, kyc, serp_source, settings)
    analysis.serp_status = outcome.status
    analysis.serp_source = outcome.source or None
    analysis.serp_hit_count = outcome.hits
    analysis.serp_query_count = outcome.queries
    analysis.serp_score = outcome.score
    analysis.status = "done"
    analysis.progress = 100
    analysis.current_step = None
    session.commit()

    return {
        "analysis_id": str(analysis.id),
        "serp_status": outcome.status,
        "serp_score": outcome.score,
        "serp_hit_count": outcome.hits,
        "serp_query_count": outcome.queries,
        "serp_source": outcome.source,
    }


def handle_geo_run(session: Session, run: ModuleRun, settings: Settings) -> dict[str, Any]:
    context = _load_brand_context(session, run)
    kyc = _kyc_from_context(context)
    kyc_step.require_usable(kyc, known_topic=context.category or "")

    payload = run.payload or {}
    prompt_specs = payload.get("prompts") or []
    if not prompt_specs:
        raise ModuleRunError("prompts are required")

    run.current_step = "execute"
    run.progress = 5
    session.commit()

    analysis = _shell_analysis(session, run, context, kind="geo_run")
    prompt_rows: list[Prompt] = []
    for spec in prompt_specs:
        text = (spec.get("text") or "").strip()
        if not text:
            raise ModuleRunError("each prompt must have text")
        row = Prompt(
            analysis_id=analysis.id,
            text=text,
            category=(spec.get("category") or "general"),
        )
        session.add(row)
        prompt_rows.append(row)
    session.flush()

    analysis = run_geo_only(session, analysis, prompt_rows, kyc, settings)
    return {
        "analysis_id": str(analysis.id),
        "geo_score": analysis.geo_score,
        "total_responses": analysis.total_responses,
        "footprint_count": analysis.footprint_count,
    }


_HANDLERS = {
    JOB_KIND_KYC_EXTRACT: handle_kyc_extract,
    JOB_KIND_SERP_RUN: handle_serp_run,
    JOB_KIND_GEO_RUN: handle_geo_run,
}


def run_module_run(session: Session, run_id: uuid.UUID, settings: Settings) -> ModuleRun:
    """Execute one claimed module run to a terminal status."""

    run = session.get(ModuleRun, run_id)
    if run is None:
        raise ModuleRunError("module run not found")

    handler = _HANDLERS.get(run.job_kind)
    if handler is None:
        raise ModuleRunError(f"unknown job kind: {run.job_kind}")

    try:
        result = handler(session, run, settings)
        run.result = result
        run.status = "done"
        run.progress = 100
        run.current_step = None
        run.error = None
        session.commit()
        return run
    except ModuleRunError as exc:
        run.status = "failed"
        run.error = str(exc)[:500]
        run.current_step = None
        session.commit()
        raise
    except Exception as exc:
        session.rollback()
        failed = session.get(ModuleRun, run_id)
        if failed is not None:
            failed.status = "failed"
            failed.error = str(exc)[:500]
            failed.current_step = None
            session.commit()
        logger.exception("module run %s failed", run_id)
        raise
