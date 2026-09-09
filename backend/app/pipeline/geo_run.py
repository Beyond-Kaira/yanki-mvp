"""Build and persist analysis-level GEO run metadata (ADR-51)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

LLM_PROVIDER = "openrouter"
SEARCH_PROVIDER_TAVILY = "tavily"


def build_geo_run(
    *,
    mode: str,
    llm_models: list[str],
    search_provider: str | None,
    schema_version: str,
) -> dict[str, Any]:
    """One run-level metadata blob stored on ``analyses.geo_run``."""

    models = [slug for slug in llm_models if slug]
    primary = models[0] if models else "openai/gpt-4o-mini"
    return {
        "mode": mode,
        "llm": {"provider": LLM_PROVIDER, "model": primary, "models": models},
        "search": {"provider": search_provider} if search_provider else None,
        "schema_version": schema_version,
        "generated_at": datetime.now(UTC).isoformat(),
    }
