"""Read builders for per-feature analysis GET slices.

Each helper mirrors the corresponding field(s) on ``ResultOut``. The main GET
returns a thin envelope via ``build_envelope()``; slice routes carry feature
payloads (analysis API split phase 2).
"""

from __future__ import annotations

from app.api.schemas import (
    AnalysisKycOut,
    AnalysisOut,
    AnalysisPromptsOut,
    CompetitorMention,
    EnginePresence,
    GeoOut,
    GeoRecordOut,
    PromptOut,
    ResponseOut,
    SeoAuditOut,
    SeoCheckOut,
    SerpCheckOut,
    SerpVisibilityOut,
)
from app.db.models import Analysis
from app.services.checker_summary import summarize_checker


def build_envelope(analysis: Analysis) -> AnalysisOut:
    """Thin poll payload — summary columns only, no nested ``result``."""
    return AnalysisOut(
        id=analysis.id,
        url=analysis.url,
        status=analysis.status,
        run_mode=analysis.run_mode or "quick",
        progress=analysis.progress,
        current_step=analysis.current_step,
        error=analysis.error,
        created_at=analysis.created_at,
        updated_at=analysis.updated_at,
        geo_score=analysis.geo_score,
        footprint_count=analysis.footprint_count,
        total_responses=analysis.total_responses,
        reliability_score=analysis.reliability_score,
        serp_status=analysis.serp_status,
        serp_score=analysis.serp_score,
        seo_status=analysis.seo_status,
        seo_score=analysis.seo_score,
        seo_grade=analysis.seo_grade,
    )


def build_kyc_out(analysis: Analysis) -> AnalysisKycOut:
    return AnalysisKycOut(kyc=analysis.kyc)


def build_prompts_out(analysis: Analysis) -> AnalysisPromptsOut:
    return AnalysisPromptsOut(
        prompts=[PromptOut.model_validate(p) for p in analysis.prompts],
    )


def build_serp_out(analysis: Analysis) -> SerpVisibilityOut | None:
    if analysis.serp_status is None:
        return None
    return SerpVisibilityOut(
        status=analysis.serp_status,
        source=analysis.serp_source,
        score=analysis.serp_score,
        hits=analysis.serp_hit_count or 0,
        queries=analysis.serp_query_count or 0,
        checks=[SerpCheckOut.model_validate(c) for c in analysis.serp_checks],
    )


def build_seo_out(analysis: Analysis) -> SeoAuditOut | None:
    if analysis.seo_status is None:
        return None
    return SeoAuditOut(
        status=analysis.seo_status,
        score=analysis.seo_score,
        grade=analysis.seo_grade,
        checks=[SeoCheckOut.model_validate(c) for c in analysis.seo_checks],
    )


def _checker_aggregates(
    analysis: Analysis,
) -> tuple[list[EnginePresence] | None, list[CompetitorMention] | None]:
    if analysis.kind != "checker":
        return None, None
    summary = summarize_checker(analysis.responses, analysis.kyc)
    engine_presence = [EnginePresence.model_validate(stat) for stat in summary.engine_presence]
    competitors_appeared = [
        CompetitorMention.model_validate(stat) for stat in summary.competitors_appeared
    ]
    return engine_presence, competitors_appeared


def build_geo_out(analysis: Analysis) -> GeoOut:
    engine_presence, competitors_appeared = _checker_aggregates(analysis)
    return GeoOut(
        responses=[ResponseOut.model_validate(r) for r in analysis.responses],
        geo_score=analysis.geo_score,
        footprint_count=analysis.footprint_count,
        total_responses=analysis.total_responses,
        reliability_score=analysis.reliability_score,
        interventions=analysis.interventions,
        citation_summary=analysis.citation_summary,
        geo_records=[GeoRecordOut.model_validate(r) for r in analysis.geo_records],
        engine_presence=engine_presence,
        competitors_appeared=competitors_appeared,
    )
