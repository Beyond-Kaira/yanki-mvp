"""Keyword-expand normalize / variant helpers."""

from __future__ import annotations

from app.keyword.normalize import (
    brand_names_to_exclusion_keys,
    collapse_keyword_whitespace,
    is_usable_phrase,
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
