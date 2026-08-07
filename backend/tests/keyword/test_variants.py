"""Smart-skip rules for local seed query variants."""

from __future__ import annotations

from app.keyword.variants import build_seed_query_variants


def test_variants_skip_when_seed_already_has_shape_prefix():
    out = build_seed_query_variants("best seo apps")
    assert "best best seo apps" not in out
    assert all(not p.lower().startswith("best best") for p in out)


def test_variants_skip_when_seed_already_has_shape_suffix():
    out = build_seed_query_variants("seo apps comparison")
    assert "seo apps comparison comparison" not in out
    assert all(not p.lower().endswith("comparison comparison") for p in out)


def test_variants_still_produce_useful_shapes_for_plain_seed():
    out = build_seed_query_variants("seo apps", limit=8)
    assert "best seo apps" in out
    assert "seo apps reviews" in out


def test_variants_empty_for_tiny_seed():
    assert build_seed_query_variants("ab") == []
    assert build_seed_query_variants("x") == []


def test_variants_empty_for_mostly_non_latin_seed():
    assert build_seed_query_variants("seo uygulamaları") == []
    assert build_seed_query_variants("検索ツール") == []


def test_variants_respect_limit():
    out = build_seed_query_variants("money transfer", limit=2)
    assert len(out) == 2
