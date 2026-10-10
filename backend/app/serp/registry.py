"""Pick the SERP source, honouring ``SERP_ENABLED`` and ``DRY_RUN``.

Mirrors ``providers/registry.py``, with one difference that matters: this one is
allowed to return ``None``. The LLM panel is the product and always has a
provider, if only a mock; SERP visibility is an *additional* surface that needs a
piece of infrastructure — a SearXNG instance — that no environment has until an
operator runs one. So it stays dark everywhere until switched on, the same
stance ``checker_enabled`` and ``emails_enabled`` take, and ``None`` is the
honest answer to "which source should this run use" when the answer is "none".
"""

from __future__ import annotations

from app.serp.base import SerpSource
from app.serp.dataforseo import DataForSeoSource
from app.serp.mock import MockSerpSource
from app.serp.searxng import SearxngSource


def _serp_provider(settings) -> str:
    return (getattr(settings, "serp_provider", "") or "searxng").strip().lower()


def get_serp_source(settings) -> SerpSource | None:
    """The source for this run, or ``None`` when SERP visibility is off."""
    if not getattr(settings, "serp_enabled", False):
        return None
    if getattr(settings, "dry_run", True):
        return MockSerpSource()

    language = getattr(settings, "serp_language", "en")
    timeout_seconds = getattr(settings, "serp_timeout_seconds", 10.0)
    max_results = getattr(settings, "serp_max_results", 20)

    if _serp_provider(settings) == "dataforseo":
        login = (getattr(settings, "dataforseo_login", "") or "").strip()
        password = (getattr(settings, "dataforseo_password", "") or "").strip()
        if not login or not password:
            return None
        location_code = getattr(settings, "dataforseo_location_code", 0) or None
        return DataForSeoSource(
            login,
            password,
            language=language,
            location_code=location_code,
            device=getattr(settings, "dataforseo_device", "desktop"),
            timeout_seconds=timeout_seconds,
            max_results=max_results,
        )

    base_url = (getattr(settings, "serp_base_url", "") or "").strip()
    if not base_url:
        # Enabled but unconfigured. Returning None (rather than a source that
        # raises on every query) keeps the failure legible: the run records
        # "not measured" instead of six identical connection errors.
        return None
    return SearxngSource(
        base_url,
        language=language,
        categories=getattr(settings, "serp_categories", "general"),
        engines=getattr(settings, "serp_engines", ""),
        safesearch=getattr(settings, "serp_safesearch", 0),
        timeout_seconds=timeout_seconds,
        max_results=max_results,
    )
