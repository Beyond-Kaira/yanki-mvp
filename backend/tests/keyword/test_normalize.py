"""Keyword-expand normalize / variant helpers."""

from __future__ import annotations

from app.keyword.normalize import (
    brand_names_to_exclusion_keys,
    collapse_keyword_whitespace,
    is_usable_phrase,
    looks_like_keyword_idea,
    looks_like_paa_idea,
    looks_like_related_keyword_idea,
    should_exclude_keyword_candidate,
)
from app.keyword.variants import build_seed_query_variants


def test_collapse_keyword_whitespace():
    assert collapse_keyword_whitespace("  money   transfer\n") == "money transfer"


def test_is_usable_phrase_rejects_urls_and_tiny_fragments():
    assert is_usable_phrase("money transfer")
    assert not is_usable_phrase("a")
    assert not is_usable_phrase("https://example.com/money")
    assert not is_usable_phrase("www.example.com")


def test_should_exclude_keyword_candidate_filters_brand_leaks():
    keys = brand_names_to_exclusion_keys(["Wise"])
    assert should_exclude_keyword_candidate("Wise money transfer", keys)
    assert not should_exclude_keyword_candidate("money transfer comparison", keys)


def test_build_seed_query_variants_are_deduped():
    variants = build_seed_query_variants("money transfer")
    assert "best money transfer" in variants
    assert "money transfer reviews" in variants
    assert "money transfer" not in variants
    assert len(variants) == len({v.lower() for v in variants})


def test_looks_like_paa_idea_requires_question_shape():
    assert looks_like_paa_idea("is money transfer safe")
    assert looks_like_paa_idea("how to send money abroad?")
    assert not looks_like_paa_idea("money transfer tips")
    assert not looks_like_paa_idea("A long prose answer that ends.")


def test_looks_like_related_requires_seed_token_coverage():
    assert looks_like_related_keyword_idea("money transfer", "Best money transfer apps")
    assert not looks_like_related_keyword_idea("money transfer", "Unrelated banking news")
    assert not looks_like_related_keyword_idea("money transfer", "money only headline")
    assert not looks_like_keyword_idea("see example.com deals")
