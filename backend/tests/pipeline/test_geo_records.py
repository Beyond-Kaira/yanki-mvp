"""Tests for geo_records persist + citation_summary aggregation."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.pipeline.geo_records import aggregate_citation_summary, geo_record_from_audit


def test_aggregate_citation_summary_rates():
    records = [
        {
            "citation_metrics": {
                "total_citations": 2,
                "target_brand_cited": True,
                "owned_media_cited": True,
                "earned_media_cited": False,
                "competitor_citation_share": {"Acme": 1},
            }
        },
        {
            "citation_metrics": {
                "total_citations": 4,
                "target_brand_cited": False,
                "owned_media_cited": False,
                "earned_media_cited": True,
                "competitor_citation_share": {"Acme": 2, "Globex": 1},
            }
        },
    ]
    summary = aggregate_citation_summary(records)
    assert summary["record_count"] == 2
    assert summary["cite_rate"] == 0.5
    assert summary["owned_rate"] == 0.5
    assert summary["earned_rate"] == 0.5
    assert summary["avg_citations"] == 3.0
    assert summary["competitor_citation_share"]["Acme"] == 3
    assert summary["competitor_citation_share"]["Globex"] == 1


def test_aggregate_citation_summary_empty():
    summary = aggregate_citation_summary([])
    assert summary["record_count"] == 0
    assert summary["cite_rate"] == 0.0
    assert summary["competitor_citation_share"] == {}


def test_pipeline_persists_geo_records_and_citation_summary(
    db_session, models, settings, monkeypatch
):
    from app.pipeline import discovery, runner

    monkeypatch.setattr(
        discovery, "discover", lambda url: "Acme builds warehouse robots and tools."
    )

    analysis = models.Analysis(url="https://example.com", status="running")
    db_session.add(analysis)
    db_session.flush()

    result = runner.run_pipeline(db_session, analysis.id, settings)

    geo_rows = (
        db_session.execute(
            select(models.GeoRecord).where(models.GeoRecord.analysis_id == analysis.id)
        )
        .scalars()
        .all()
    )
    assert len(geo_rows) == settings.prompt_count
    assert all(row.brand for row in geo_rows)
    assert all(row.prompt for row in geo_rows)
    assert all(row.citation_metrics is not None for row in geo_rows)
    assert all(row.response_id is not None for row in geo_rows)

    assert result.citation_summary is not None
    assert result.citation_summary["record_count"] == settings.prompt_count
    assert "cite_rate" in result.citation_summary


def test_geo_record_from_audit_maps_kaira_keys():
    analysis_id = uuid.uuid4()
    response_id = uuid.uuid4()
    record = {
        "brand": "Acme",
        "sector": "industrial",
        "prompt": "best warehouse robots?",
        "prompt_group": "discovery",
        "intent": "informational",
        "measurement_mode": "mock",
        "search_provider": "mock",
        "search_results": [{"rank": 1}],
        "search_visibility": {"brand_in_results": True},
        "grounded_answer": "Acme is strong.",
        "simulated_answer": "Acme is strong.",
        "mentioned": True,
        "rank_position": 1,
        "mention_context": "primary_recommendation",
        "competitors": ["Globex"],
        "answer_summary": "Acme leads.",
        "recommendation_reasoning": "Strong product.",
        "reasoning_trace": {"confidence": 0.9},
        "citations": [{"source_domain": "acme.example"}],
        "citation_metrics": {"total_citations": 1, "target_brand_cited": True},
        "visibility_drivers": {"brand_strength": ["known"]},
        "visibility_gaps": {"content_gap": []},
        "trust_signals": ["reviews"],
        "entities_associated_with_brand": ["robots"],
        "sentiment": "positive",
        "content_improvement_opportunities": ["more guides"],
        "model": "mock",
        "generated_at": "2026-08-03T10:00:00+00:00",
        "error": False,
        "schema_version": "3.0",
        "owned_domains": ["acme.example"],
    }
    row = geo_record_from_audit(
        record, analysis_id=analysis_id, response_id=response_id
    )
    assert row.brand == "Acme"
    assert row.mentioned is True
    assert row.citations == [{"source_domain": "acme.example"}]
    assert row.citation_metrics["target_brand_cited"] is True
    assert row.owned_domains == ["acme.example"]
    assert row.generated_at is not None


def test_geo_record_coerces_string_list_fields():
    from app.api.schemas import GeoRecordOut

    row = geo_record_from_audit(
        {
            "brand": "Acme",
            "prompt": "q",
            "content_improvement_opportunities": "Write more comparison pages.",
            "competitors": "Globex",
            "trust_signals": "regulated",
        },
        analysis_id=uuid.uuid4(),
        response_id=uuid.uuid4(),
    )
    assert row.content_improvement_opportunities == ["Write more comparison pages."]
    assert row.competitors == ["Globex"]
    assert row.trust_signals == ["regulated"]

    out = GeoRecordOut.model_validate(
        {
            "id": uuid.uuid4(),
            "response_id": uuid.uuid4(),
            "brand": "Acme",
            "prompt": "q",
            "content_improvement_opportunities": "Write more comparison pages.",
        }
    )
    assert out.content_improvement_opportunities == ["Write more comparison pages."]
