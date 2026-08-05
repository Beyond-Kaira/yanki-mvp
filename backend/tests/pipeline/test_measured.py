from __future__ import annotations

from app.pipeline.measured import measure_search_visibility, run_measured_audit
from app.providers.tavily import mock_search


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
