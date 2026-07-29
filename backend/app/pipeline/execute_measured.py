"""Step 4 — GEO execute: measured (Tavily) or simulated (OpenRouter-only).

Mode is selected by ``settings.geo_mode`` (``measured`` | ``simulated``).
Each prompt becomes one ``responses`` row with ``engine`` matching the mode,
``raw_text`` = answer text, ``footprint`` = mentioned, ``audit`` = full record.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.db.models import Response
from app.pipeline import measured as measured_step
from app.pipeline import simulated as simulated_step
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


def run_measured_execute(session, analysis, prompt_rows, settings) -> list[Response]:
    """Run measured or simulated audits for every prompt; persist Response rows."""
    ctx = _brand_context(analysis.kyc, analysis.url)
    dry_run = bool(getattr(settings, "dry_run", True))
    mode = _geo_mode(settings)

    llm = None
    search = None
    if not dry_run:
        from app.providers.openrouter import OpenRouterProvider
        from app.providers.tavily import TavilyClient

        llm = OpenRouterProvider(
            api_key=getattr(settings, "open_router_key", ""),
            model=getattr(settings, "openrouter_model", "openai/gpt-4o-mini"),
        )
        if mode == "measured":
            search = TavilyClient(api_key=getattr(settings, "tavily_api_key", ""))

    rows: list[Response] = []
    max_responses = int(getattr(settings, "max_responses_per_job", 60) or 60)

    for prompt in prompt_rows:
        if len(rows) >= max_responses:
            break

        if mode == "simulated":
            record = simulated_step.run_simulated_audit(
                brand=ctx["brand"],
                prompt=prompt.text,
                prompt_group=prompt.category or "general",
                owned_domains=ctx["owned_domains"],
                aliases=ctx["aliases"],
                sector=ctx["sector"],
                llm=llm,
                dry_run=dry_run,
            )
            engine = "simulated"
        else:
            record = measured_step.run_measured_audit(
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
            )
            engine = "measured"

        mentioned = bool(record.get("mentioned"))
        grounded = (
            record.get("grounded_answer")
            or record.get("simulated_answer")
            or ""
        )
        if not grounded:
            grounded = _error_text(record)
        snippet = grounded[:200] if mentioned and grounded else None

        model_name = record.get("model") or (
            getattr(settings, "openrouter_model", "openai/gpt-4o-mini")
            if not dry_run
            else "mock"
        )

        row = Response(
            analysis_id=analysis.id,
            prompt_id=prompt.id,
            engine=engine,
            model=model_name,
            raw_text=grounded,
            footprint=mentioned,
            matched_snippet=snippet,
            audit=record,
            cost_usd=Decimal("0"),
        )
        session.add(row)
        rows.append(row)
        session.flush()

    return rows


def _error_text(record: dict[str, Any]) -> str:
    if record.get("error"):
        return (
            f"[geo error] {record.get('error_stage')}: "
            f"{record.get('error_response')}"
        )
    return ""
