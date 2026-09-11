"""Pick which providers to use, honouring DRY_RUN.

Measured GEO path uses OpenRouter for all LLM calls (KYC + grounded + audit)
and Tavily for search. Legacy multi-engine panel helpers remain for transitional
tests until execute.py is fully removed.
"""

from __future__ import annotations

from app.providers.base import Provider
from app.providers.mock import MockProvider

DEFAULT_PANEL = ["anthropic", "openai", "gemini", "perplexity"]


def _panel_engines(settings) -> list[str]:
    raw = getattr(settings, "panel_engines", None) or ",".join(DEFAULT_PANEL)
    return [engine.strip() for engine in raw.split(",") if engine.strip()]


def _build_real(engine: str, settings) -> Provider:
    if engine == "anthropic":
        from app.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider(api_key=getattr(settings, "anthropic_api_key", ""))
    if engine == "openai":
        from app.providers.openai_provider import OpenAIProvider

        return OpenAIProvider(api_key=getattr(settings, "openai_api_key", ""))
    if engine == "gemini":
        from app.providers.gemini_provider import GeminiProvider

        return GeminiProvider(api_key=getattr(settings, "gemini_api_key", ""))
    if engine == "perplexity":
        from app.providers.perplexity_provider import PerplexityProvider

        return PerplexityProvider(api_key=getattr(settings, "perplexity_api_key", ""))
    if engine == "openrouter":
        from app.providers.openrouter import OpenRouterProvider

        return OpenRouterProvider(
            api_key=getattr(settings, "open_router_key", ""),
            model=getattr(settings, "openrouter_model", "openai/gpt-4o-mini"),
        )
    return MockProvider(engine)


def get_panel(settings) -> list[Provider]:
    """Legacy multi-engine panel (tests / transitional). Prefer measured path."""
    engines = _panel_engines(settings)
    if getattr(settings, "dry_run", True):
        return [MockProvider(engine) for engine in engines]
    return [_build_real(engine, settings) for engine in engines]


def get_analysis_provider(settings) -> Provider:
    """KYC LLM: OpenRouter in live mode, mock under DRY_RUN."""
    if getattr(settings, "dry_run", True):
        return MockProvider("mock")
    return _build_real("openrouter", settings)


def get_openrouter_models(settings) -> list[str]:
    """OpenRouter model slugs for GEO multi-LLM fan-out (measured + simulated)."""

    if hasattr(settings, "geo_llm_model_list"):
        return settings.geo_llm_model_list()
    raw = getattr(settings, "geo_llm_models", None)
    if raw:
        from app.config import parse_geo_llm_model_list

        return parse_geo_llm_model_list(
            str(raw),
            fallback_model=getattr(settings, "openrouter_model", "openai/gpt-4o-mini"),
        )
    # Transitional: duck-typed settings in older tests.
    return [getattr(settings, "openrouter_model", "openai/gpt-4o-mini")]


def get_measured_llm(settings, *, model: str | None = None):
    """OpenRouter chat client for grounded answer + audit extraction."""
    if getattr(settings, "dry_run", True):
        return None
    from app.providers.openrouter import OpenRouterProvider

    if model is not None:
        slug = model
    else:
        configured = getattr(settings, "openrouter_model", "openai/gpt-4o-mini")
        slug = (
            configured
            if isinstance(configured, str) and configured.strip()
            else "openai/gpt-4o-mini"
        )
    return OpenRouterProvider(
        api_key=getattr(settings, "open_router_key", ""),
        model=slug,
    )


def get_search_client(settings):
    """Tavily client for measured search; None under DRY_RUN (mock_search used)."""
    if getattr(settings, "dry_run", True):
        return None
    from app.providers.tavily import TavilyClient

    return TavilyClient(api_key=getattr(settings, "tavily_api_key", ""))
