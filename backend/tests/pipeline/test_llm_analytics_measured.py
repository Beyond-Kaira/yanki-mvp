from __future__ import annotations

import json

from app.pipeline.llm_analytics_measured import (
    AUDIT_EXTRACTION_SYSTEM_PROMPT,
    GROUNDED_ANSWER_SYSTEM_PROMPT,
    measure_search_visibility,
    run_measured_audit,
    run_measured_audits,
)
from app.providers.tavily import mock_search


class _CountingLLM:
    model: str
    audit_calls = 0
    grounded_calls = 0

    def __init__(self, model: str) -> None:
        self.model = model

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 3000,
        json_object: bool = True,
    ):
        system = messages[0]["content"]
        if system == AUDIT_EXTRACTION_SYSTEM_PROMPT:
            type(self).audit_calls += 1
            payload = {
                "intent": "informational",
                "mention_context": "not_mentioned",
                "recommendation_reasoning": f"audit from {self.model}",
                "reasoning_trace": {
                    "search_findings": "x",
                    "answer_findings": "x",
                    "brand_evaluation": "x",
                    "confidence": 0.5,
                },
                "visibility_drivers": {},
                "visibility_gaps": {},
                "trust_signals": [],
                "entities_associated_with_brand": [],
                "sentiment": "neutral",
                "content_improvement_opportunities": [],
            }
        elif system.strip() == GROUNDED_ANSWER_SYSTEM_PROMPT.strip():
            type(self).grounded_calls += 1
            payload = {
                "grounded_answer": "Leaders include Acme [1].",
                "citations": [],
                "competitors": ["Acme"],
                "answer_summary": "summary",
            }
        else:
            raise AssertionError(f"unexpected system prompt: {system[:40]!r}")

        class _Result:
            text = json.dumps(payload)
            cost_usd = 0.001

        return _Result()


def test_dry_run_measured_audit_returns_record():
    record = run_measured_audit(
        brand="Yanki Demo Co",
        prompt="Best analytics tools",
        prompt_group="recommendation",
        owned_domains=["yankidemoco.example"],
        aliases=["Yanki"],
        known_competitors=["Acme", "Globex"],
        sector="Software",
        dry_run=True,
    )
    assert record["error"] is False
    assert record["brand"] == "Yanki Demo Co"
    assert "citation_metrics" in record
    assert record["mention_context"] in {
        "primary_recommendation",
        "secondary_recommendation",
        "comparison_candidate",
        "alternative_option",
        "competitor_only",
        "not_mentioned",
    }


def test_search_visibility_detects_owned_domain():
    payload = mock_search("query", brand="Acme")
    # Force owned domain match on first result.
    payload["results"][0]["domain"] = "acme.com"
    payload["results"][0]["brands_mentioned"] = []
    visibility = measure_search_visibility(
        "Acme",
        payload,
        owned_domains=["acme.com"],
        aliases=[],
    )
    assert visibility["owned_domain_in_results"] is True
    assert visibility["brand_in_results"] is True


def test_run_measured_audits_dry_run_returns_one_record_per_model_slug():
    slugs = [
        "openai/gpt-4o-mini",
        "anthropic/claude-3.5-sonnet",
        "google/gemini-2.0-flash-001",
    ]
    records = run_measured_audits(
        brand="Yanki Demo Co",
        prompt="Best analytics tools",
        prompt_group="recommendation",
        owned_domains=["yankidemoco.example"],
        dry_run=True,
        model_slugs=slugs,
    )
    assert len(records) == 3
    assert [record["model"] for record in records] == slugs
    assert all(record["error"] is False for record in records)
    assert records[0]["grounded_answer"] == records[1]["grounded_answer"]


def test_run_measured_audits_live_calls_audit_once_per_model():
    _CountingLLM.audit_calls = 0
    _CountingLLM.grounded_calls = 0
    slugs = ["openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet"]

    def factory(slug: str) -> _CountingLLM:
        return _CountingLLM(slug)

    records = run_measured_audits(
        brand="Acme",
        prompt="Best tools",
        prompt_group="recommendation",
        owned_domains=["acme.com"],
        dry_run=False,
        model_slugs=slugs,
        llm_factory=factory,
        search_payload=mock_search("Best tools", brand="Acme"),
    )
    assert len(records) == 2
    assert _CountingLLM.grounded_calls == 1
    assert _CountingLLM.audit_calls == 2
    assert records[0]["model"] == slugs[0]
    assert records[1]["recommendation_reasoning"] == f"audit from {slugs[1]}"


def test_run_measured_audit_remains_single_record_wrapper():
    record = run_measured_audit(
        brand="Yanki Demo Co",
        prompt="Best analytics tools",
        prompt_group="recommendation",
        owned_domains=["yankidemoco.example"],
        dry_run=True,
    )
    assert record["model"] == "mock"
