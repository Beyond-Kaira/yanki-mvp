from __future__ import annotations

import json

from app.pipeline.llm_analytics_measured import (
    AUDIT_EXTRACTION_SYSTEM_PROMPT,
    CITATION_MARKER_REPAIR_SYSTEM_PROMPT,
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
                "grounded_answer": f"Leaders include Acme [1]. (via {self.model})",
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


class _MarkerRepairLLM:
    model = "openai/gpt-4o-mini"

    def __init__(self, *, valid_repair: bool) -> None:
        self.valid_repair = valid_repair
        self.repair_calls = 0

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 3000,
        json_object: bool = True,
    ):
        system = messages[0]["content"]
        if system.strip() == GROUNDED_ANSWER_SYSTEM_PROMPT.strip():
            payload = {
                "grounded_answer": "Acme is recommended by the supplied sources.",
                "citations": [{"result_rank": 1}, {"result_rank": 2}],
                "competitors": [],
                "answer_summary": "summary",
            }
        elif system == CITATION_MARKER_REPAIR_SYSTEM_PROMPT:
            self.repair_calls += 1
            payload = {
                "grounded_answer": (
                    "Acme is recommended by the supplied sources [1, 2]."
                    if self.valid_repair
                    else "Acme and Globex are recommended by the supplied sources [1, 2]."
                )
            }
        elif system == AUDIT_EXTRACTION_SYSTEM_PROMPT:
            payload = {
                "intent": "informational",
                "mention_context": "primary_recommendation",
                "recommendation_reasoning": "supported",
                "reasoning_trace": {},
                "visibility_drivers": {},
                "visibility_gaps": {},
                "trust_signals": [],
                "entities_associated_with_brand": [],
                "sentiment": "neutral",
                "content_improvement_opportunities": [],
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
        "anthropic/claude-sonnet-4.5",
        "google/gemini-2.5-flash",
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
    assert len({record["grounded_answer"] for record in records}) == len(slugs)


def test_run_measured_audits_live_calls_grounded_and_audit_once_per_model():
    _CountingLLM.audit_calls = 0
    _CountingLLM.grounded_calls = 0
    slugs = ["openai/gpt-4o-mini", "anthropic/claude-sonnet-4.5"]

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
    assert _CountingLLM.grounded_calls == 2
    assert _CountingLLM.audit_calls == 2
    assert records[0]["model"] == slugs[0]
    assert records[0]["grounded_answer"] != records[1]["grounded_answer"]
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


def test_live_run_repairs_missing_inline_citation_markers_once():
    llm = _MarkerRepairLLM(valid_repair=True)
    record = run_measured_audits(
        brand="Acme",
        prompt="Best tools",
        prompt_group="recommendation",
        owned_domains=["acme.com"],
        llm=llm,
        dry_run=False,
        model_slugs=[llm.model],
        search_payload=mock_search("Best tools", brand="Acme"),
    )[0]

    assert llm.repair_calls == 1
    assert record["grounded_answer"].endswith("[1, 2].")
    assert record["citation_quality"] == {
        "status": "valid",
        "cited_ranks": [1, 2],
        "inline_ranks": [1, 2],
        "missing_inline_ranks": [],
        "unexpected_inline_ranks": [],
        "initial_status": "missing_inline_markers",
        "repair_attempted": True,
        "repair_succeeded": True,
    }
    assert record["_cost_usd"] == 0.003


def test_failed_marker_repair_keeps_original_answer_and_quality_state():
    llm = _MarkerRepairLLM(valid_repair=False)
    record = run_measured_audits(
        brand="Acme",
        prompt="Best tools",
        prompt_group="recommendation",
        owned_domains=["acme.com"],
        llm=llm,
        dry_run=False,
        model_slugs=[llm.model],
        search_payload=mock_search("Best tools", brand="Acme"),
    )[0]

    assert llm.repair_calls == 1
    assert record["grounded_answer"] == "Acme is recommended by the supplied sources."
    assert record["citation_quality"]["status"] == "repair_failed"
    assert record["citation_quality"]["missing_inline_ranks"] == [1, 2]
    assert record["citation_quality"]["repair_succeeded"] is False
    assert record["citation_quality"]["repair_rejection"] == "answer_content_changed"
    assert record["_cost_usd"] == 0.003
