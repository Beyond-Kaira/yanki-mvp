"""Step 4 — GEO execute: measured (Tavily) or simulated (OpenRouter-only).

Mode is selected by ``settings.geo_mode`` (``measured`` | ``simulated``).
Run metadata is stored once on ``analyses.geo_run``; each prompt × model slug
becomes one ``responses`` row with ``llm_provider=openrouter``, ``model`` = slug,
``raw_text`` = answer text, ``footprint`` = mentioned, ``audit`` = full record.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from app.db.models import Response
from app.pipeline import geo_records as geo_records_step
from app.pipeline import llm_analytics_measured as llm_analytics_measured_step
from app.pipeline import simulated as simulated_step
from app.pipeline.geo_run import LLM_PROVIDER, SEARCH_PROVIDER_TAVILY, build_geo_run
from app.pipeline.llm_analytics_measured import SCHEMA_VERSION
from app.providers.registry import get_openrouter_models, get_measured_llm
from app.providers.tavily import owned_domains_from_url


def _brand_context(kyc: dict[str, Any] | None, url: str) -> dict[str, Any]:
    profile = kyc or {}
    brand = (profile.get("company") or "").strip() or "Unknown"
    aliases = [a for a in (profile.get("aliases") or []) if a]
    competitors = [c for c in (profile.get("competitors") or []) if c]
    owned = owned_domains_from_url(url)
    return {
        "brand": brand,
        "aliases": aliases,
        "competitors": competitors,
        "owned_domains": owned,
        "sector": (profile.get("industry") or "").strip(),
    }


def _geo_mode(settings) -> str:
    mode = (getattr(settings, "geo_mode", None) or "measured").strip().lower()
    if mode not in {"measured", "simulated"}:
        return "measured"
    return mode


def _persist_response_row(
    session,
    analysis,
    prompt,
    record: dict[str, Any],
    *,
    settings,
    rows: list[Response],
) -> Response:
    mentioned = bool(record.get("mentioned"))
    grounded = record.get("grounded_answer") or record.get("simulated_answer") or ""
    if not grounded:
        grounded = _error_text(record)
    snippet = grounded[:200] if mentioned and grounded else None

    model_name = record.get("model") or (
        getattr(settings, "openrouter_model", "openai/gpt-4o-mini")
        if not getattr(settings, "dry_run", True)
        else "mock"
    )

    row = Response(
        analysis_id=analysis.id,
        prompt_id=prompt.id,
        llm_provider=LLM_PROVIDER,
        model=model_name,
        raw_text=grounded,
        footprint=mentioned,
        matched_snippet=snippet,
        audit=record,
        cost_usd=_record_cost(record),
    )
    session.add(row)
    rows.append(row)
    session.flush()
    session.add(
        geo_records_step.geo_record_from_audit(
            record,
            analysis_id=analysis.id,
            response_id=row.id,
        )
    )
    session.flush()
    return row


def run_measured_execute(session, analysis, prompt_rows, settings) -> list[Response]:
    """Run measured or simulated audits for every prompt; persist Response rows."""
    ctx = _brand_context(analysis.kyc, analysis.url)
    dry_run = bool(getattr(settings, "dry_run", True))
    mode = _geo_mode(settings)
    model_slugs = get_openrouter_models(settings)

    llm = None
    search = None
    if not dry_run:
        from app.providers.tavily import TavilyClient

        llm = get_measured_llm(settings, model=model_slugs[0])
        if mode == "measured":
            search = TavilyClient(
                api_key=getattr(settings, "tavily_api_key", ""),
                search_price_usd=float(getattr(settings, "tavily_search_usd", 0.008) or 0.0),
            )

    rows: list[Response] = []
    max_responses = int(getattr(settings, "max_responses_per_job", 60) or 60)
    analysis.geo_run = build_geo_run(
        mode=mode,
        llm_models=model_slugs,
        search_provider=SEARCH_PROVIDER_TAVILY if mode == "measured" else None,
        schema_version=SCHEMA_VERSION,
    )
    session.flush()

    for prompt in prompt_rows:
        if len(rows) >= max_responses:
            break

        if mode == "simulated":
            records = simulated_step.run_simulated_audits(
                brand=ctx["brand"],
                prompt=prompt.text,
                prompt_group=prompt.category or "general",
                owned_domains=ctx["owned_domains"],
                aliases=ctx["aliases"],
                sector=ctx["sector"],
                llm=llm,
                dry_run=dry_run,
                model_slugs=model_slugs,
            )
            for record in records:
                if len(rows) >= max_responses:
                    break
                _persist_response_row(
                    session, analysis, prompt, record, settings=settings, rows=rows
                )
            continue

        records = llm_analytics_measured_step.run_measured_audits(
            brand=ctx["brand"],
            prompt=prompt.text,
            prompt_group=prompt.category or "general",
            owned_domains=ctx["owned_domains"],
            aliases=ctx["aliases"],
            known_competitors=ctx["competitors"],
            sector=ctx["sector"],
            llm=llm,
            search=search,
            dry_run=dry_run,
            model_slugs=model_slugs,
        )
        for record in records:
            if len(rows) >= max_responses:
                break
            _persist_response_row(session, analysis, prompt, record, settings=settings, rows=rows)

    return rows


def _record_cost(record: dict[str, Any]) -> Decimal:
    """What this audit cost, as the Numeric(10,6) column wants it.

    The measured/simulated steps already priced every provider call they made;
    until session 21 this function did not exist and the column was written as a
    literal ``Decimal("0")``, so the live default path recorded no spend at all
    and the daily USD cap — which sums exactly this column — could never trip.

    Goes through ``str()`` rather than ``Decimal(float)`` so the stored value is
    the decimal the provider quoted, not its binary-float neighbour, and clamps
    negatives: a vendor that reports nonsense should not be able to buy back
    budget already spent.
    """

    try:
        cost = Decimal(str(record.get("_cost_usd") or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")
    if cost < 0:
        return Decimal("0")
    return cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def _error_text(record: dict[str, Any]) -> str:
    if record.get("error"):
        return f"[geo error] {record.get('error_stage')}: {record.get('error_response')}"
    return ""
