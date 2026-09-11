"""GEO_LLM_MODELS config parsing (Phase 1 multi-LLM)."""

from app.config import DEFAULT_GEO_LLM_MODELS, Settings, parse_geo_llm_model_list
from app.providers.registry import get_openrouter_models


def test_default_settings_expose_three_model_slugs() -> None:
    settings = Settings()
    slugs = settings.geo_llm_model_list()
    assert len(slugs) >= 2
    assert slugs[0] == "openai/gpt-4o-mini"
    assert "anthropic/claude-sonnet-4.5" in slugs
    assert "google/gemini-2.5-flash" in slugs


def test_registry_delegates_to_settings_list() -> None:
    settings = Settings(
        geo_llm_models="openai/gpt-4o-mini,anthropic/claude-sonnet-4.5",
    )
    assert get_openrouter_models(settings) == [
        "openai/gpt-4o-mini",
        "anthropic/claude-sonnet-4.5",
    ]


def test_empty_geo_llm_models_falls_back_to_openrouter_model() -> None:
    settings = Settings(geo_llm_models="", openrouter_model="google/gemini-2.5-flash")
    assert settings.geo_llm_model_list() == ["google/gemini-2.5-flash"]


def test_parse_dedupes_and_strips_whitespace() -> None:
    raw = " openai/gpt-4o-mini , anthropic/claude-sonnet-4.5 ,openai/gpt-4o-mini "
    assert parse_geo_llm_model_list(raw, fallback_model="ignored") == [
        "openai/gpt-4o-mini",
        "anthropic/claude-sonnet-4.5",
    ]


def test_parse_blank_uses_fallback_model() -> None:
    assert parse_geo_llm_model_list("", fallback_model="mistral/mistral-small") == [
        "mistral/mistral-small"
    ]


def test_default_constant_matches_settings_default() -> None:
    assert Settings().geo_llm_models == DEFAULT_GEO_LLM_MODELS
