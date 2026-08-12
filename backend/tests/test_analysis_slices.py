"""Additive GET slices for analyses (phase 1 of analysis API split)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.db.models import Prompt, Response, SerpCheck, SeoCheck


@pytest.fixture()
def done_analysis(db_session, make_analysis):
    analysis = make_analysis(
        url="https://acme.test",
        status="done",
        progress=100,
        kyc={"company": "Acme", "industry": "Robotics", "category": "warehouse robots"},
        geo_score=72.5,
        footprint_count=1,
        total_responses=1,
        reliability_score=0.9,
        interventions=[{"id": "fix-meta", "title": "Improve meta"}],
        citation_summary={"cite_rate": 0.4},
        serp_status="ok",
        serp_source="searxng",
        serp_score=0.33,
        serp_hit_count=2,
        serp_query_count=6,
        seo_status="ok",
        seo_score=97.8,
        seo_grade="A",
    )
    prompt = Prompt(
        analysis_id=analysis.id,
        text="Best warehouse robots?",
        category="recommendation",
    )
    db_session.add(prompt)
    db_session.flush()
    db_session.add(
        Response(
            analysis_id=analysis.id,
            prompt_id=prompt.id,
            engine="measured",
            model="gpt-test",
            raw_text="Acme is strong.",
            footprint=True,
            matched_snippet="Acme",
            cost_usd=Decimal("0.001"),
            audit={"mentioned": True},
        )
    )
    db_session.add(
        SerpCheck(
            analysis_id=analysis.id,
            query="best warehouse robots",
            source="searxng",
            hit=True,
            rank=3,
            matched_url="https://acme.test",
            matched_snippet="Acme robots",
            matched_via="title",
            result_count=10,
        )
    )
    db_session.add(
        SeoCheck(
            analysis_id=analysis.id,
            check_id="robots_txt",
            title="Robots.txt",
            severity="critical",
            status="pass",
            detail="Allows crawlers",
            evidence="User-agent: *",
        )
    )
    db_session.commit()
    return analysis


def test_slice_routes_return_404_for_unknown_id(client):
    missing = uuid.uuid4()
    for path in ("/kyc", "/prompts", "/geo", "/serp", "/seo"):
        resp = client.get(f"/api/v1/analyses/{missing}{path}")
        assert resp.status_code == 404, path


def test_kyc_slice_matches_full_get(client, done_analysis):
    full = client.get(f"/api/v1/analyses/{done_analysis.id}").json()
    slice_body = client.get(f"/api/v1/analyses/{done_analysis.id}/kyc").json()
    assert slice_body == {"kyc": full["result"]["kyc"]}


def test_prompts_slice_matches_full_get(client, done_analysis):
    full = client.get(f"/api/v1/analyses/{done_analysis.id}").json()
    slice_body = client.get(f"/api/v1/analyses/{done_analysis.id}/prompts").json()
    assert slice_body["prompts"] == full["result"]["prompts"]


def test_geo_slice_matches_full_get(client, done_analysis):
    full = client.get(f"/api/v1/analyses/{done_analysis.id}").json()["result"]
    geo = client.get(f"/api/v1/analyses/{done_analysis.id}/geo").json()
    for key in (
        "responses",
        "geo_score",
        "footprint_count",
        "total_responses",
        "reliability_score",
        "interventions",
        "citation_summary",
        "geo_records",
        "engine_presence",
        "competitors_appeared",
    ):
        assert geo[key] == full[key], key


def test_serp_slice_matches_full_get(client, done_analysis):
    full = client.get(f"/api/v1/analyses/{done_analysis.id}").json()["result"]["serp"]
    serp = client.get(f"/api/v1/analyses/{done_analysis.id}/serp").json()
    assert serp == full
    assert serp["checks"][0]["query"] == "best warehouse robots"


def test_seo_slice_matches_full_get(client, done_analysis):
    full = client.get(f"/api/v1/analyses/{done_analysis.id}").json()["result"]["seo"]
    seo = client.get(f"/api/v1/analyses/{done_analysis.id}/seo").json()
    assert seo == full
    assert seo["checks"][0]["check_id"] == "robots_txt"


def test_serp_and_seo_slices_are_null_when_not_measured(client, make_analysis):
    analysis = make_analysis()
    assert client.get(f"/api/v1/analyses/{analysis.id}/serp").json() is None
    assert client.get(f"/api/v1/analyses/{analysis.id}/seo").json() is None


def test_main_get_unchanged_after_slice_routes(client, make_analysis):
    """Regression: full envelope shape is identical to pre-split behaviour."""
    analysis = make_analysis(url="https://example.test")

    resp = client.get(f"/api/v1/analyses/{analysis.id}")
    body = resp.json()
    assert "result" in body
    assert body["result"]["kyc"] is None
    assert body["result"]["prompts"] == []
    assert body["result"]["serp"] is None
    assert body["result"]["seo"] is None
