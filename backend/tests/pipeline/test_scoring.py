from __future__ import annotations

import pytest

from app.pipeline.scoring import (
    citation_weight,
    geo_score,
    mention_rate,
    per_prompt_score,
    position_weight,
    sentiment_weight,
)


def test_mention_rate_is_footprints_over_total():
    assert mention_rate(9, 20) == pytest.approx(0.45)
    assert mention_rate(5, 5) == 1.0
    assert mention_rate(0, 10) == 0.0
    assert mention_rate(0, 0) == 0.0
    assert mention_rate(3, 0) == 0.0


def test_position_and_citation_weights():
    assert position_weight("primary_recommendation") == 1.0
    assert position_weight("not_mentioned") == 0.0
    assert citation_weight(
        mentioned=True, target_brand_cited=True, owned_media_cited=True
    ) == 1.0
    assert citation_weight(
        mentioned=True, target_brand_cited=True, owned_media_cited=False
    ) == 0.85
    assert citation_weight(
        mentioned=True, target_brand_cited=False, owned_media_cited=False
    ) == 0.6
    assert citation_weight(
        mentioned=False, target_brand_cited=False, owned_media_cited=False
    ) == 0.0


def test_sentiment_falls_back_when_reliability_low():
    assert sentiment_weight("negative") == 0.5
    assert sentiment_weight("negative", reliability_score=0.2) == 0.9


def test_per_prompt_zero_when_not_mentioned():
    assert per_prompt_score({"mentioned": False, "mention_context": "primary_recommendation"}) == 0.0


def test_geo_score_composite_ignores_gap_count():
    base = {
        "mentioned": True,
        "mention_context": "primary_recommendation",
        "citation_metrics": {
            "target_brand_cited": True,
            "owned_media_cited": False,
        },
        "sentiment": "positive",
        "visibility_gaps": {"low_discoverability": ["a", "b", "c", "d", "e"]},
    }
    few_gaps = {**base, "visibility_gaps": {"low_discoverability": ["a"]}}
    assert geo_score([base]) == geo_score([few_gaps])
    # 1.0 * 1.0 * 0.85 * 1.0 * 100
    assert geo_score([base]) == pytest.approx(85.0)


def test_geo_score_averages_and_clamps():
    hit = {
        "mentioned": True,
        "mention_context": "primary_recommendation",
        "citation_metrics": {
            "target_brand_cited": True,
            "owned_media_cited": True,
        },
        "sentiment": "positive",
    }
    miss = {"mentioned": False, "mention_context": "not_mentioned"}
    assert geo_score([hit, miss]) == pytest.approx(50.0)
    assert geo_score([]) == 0.0
