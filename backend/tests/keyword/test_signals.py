"""Estimated keyword signals (intent / demand / difficulty proxies)."""

from __future__ import annotations

from app.keyword.intent import (
    INTENT_COMMERCIAL,
    INTENT_INFORMATIONAL,
    INTENT_TRANSACTIONAL,
    classify_keyword_search_intent,
)
from app.keyword.signals import (
    build_estimated_keyword_idea_signals,
    estimated_demand_score_for_discovery_source,
    estimated_difficulty_score_from_seed_serp,
)
from app.serp.base import SerpPage, SerpResult


def test_classify_keyword_search_intent_rules():
    assert classify_keyword_search_intent("how to send money") == INTENT_INFORMATIONAL
    assert classify_keyword_search_intent("best money transfer") == INTENT_COMMERCIAL
    assert classify_keyword_search_intent("cheap money transfer") == INTENT_TRANSACTIONAL


def test_estimated_demand_ranks_suggestions_above_variants():
    assert estimated_demand_score_for_discovery_source("suggestion") > (
        estimated_demand_score_for_discovery_source("variant")
    )


def test_estimated_difficulty_rises_with_hard_serp_hosts():
    soft = SerpPage(
        query="x",
        results=(
            SerpResult(rank=1, url="https://small-blog.example/a", title="a"),
            SerpResult(rank=2, url="https://local-shop.example/b", title="b"),
        ),
    )
    hard = SerpPage(
        query="x",
        results=(
            SerpResult(rank=1, url="https://en.wikipedia.org/wiki/X", title="x"),
            SerpResult(rank=2, url="https://www.amazon.com/x", title="x"),
            SerpResult(rank=3, url="https://www.forbes.com/x", title="x"),
        ),
    )
    soft_score = estimated_difficulty_score_from_seed_serp(soft)
    hard_score = estimated_difficulty_score_from_seed_serp(hard)
    assert soft_score is not None and hard_score is not None
    assert hard_score > soft_score


def test_build_estimated_keyword_idea_signals_marks_estimated():
    page = SerpPage(
        query="money transfer",
        results=(SerpResult(rank=1, url="https://en.wikipedia.org/wiki/MT", title="MT"),),
    )
    signals = build_estimated_keyword_idea_signals(
        phrase="best money transfer",
        discovery_source="suggestion",
        seed_serp_page=page,
    )
    assert signals["volume_estimated"] is True
    assert signals["difficulty_estimated"] is True
    assert signals["difficulty_basis"] == "seed_serp"
    assert signals["intent"] == INTENT_COMMERCIAL
    assert signals["estimated_demand_score"] == 78
    assert isinstance(signals["estimated_difficulty_score"], int)
