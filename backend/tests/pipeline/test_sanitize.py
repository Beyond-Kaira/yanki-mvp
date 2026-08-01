"""Value hygiene: the normalized key, junk filtering, dedupe and caps."""

from __future__ import annotations

import pytest

from app.pipeline.sanitize import (
    clean_str,
    clean_values,
    contains,
    is_junk,
    normalize_key,
)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Coca-Cola", "coca cola"),
        ("Globex Robotics A.Ş.", "globex robotics a s"),
        ("Türk Holding", "Turk Holding"),
        ("İşbank", "isbank"),
        ("ACME_ROBOTICS", "acme robotics"),
    ],
)
def test_spellings_that_must_share_one_key(left, right):
    # One identity for dedupe, grounding and brand-leak detection — if these
    # disagreed, a name could ground under one spelling and leak under another.
    assert normalize_key(left) == normalize_key(right)


def test_contains_matches_whole_words_only():
    haystack = normalize_key("General Electric makes turbines")
    assert contains(haystack, "General Electric")
    assert contains(haystack, "turbines")
    # The reason footprint keeps a word-boundary anchor: "GE" is not in
    # "General", and a two-letter brand must not ground itself inside a word.
    assert not contains(haystack, "GE")
    assert not contains(haystack, "")


def test_contains_tolerates_separator_and_diacritic_spellings():
    haystack = normalize_key("We distribute Coca-Cola and Nestlé products")
    assert contains(haystack, "Coca Cola")
    assert contains(haystack, "Nestle")


@pytest.mark.parametrize(
    "value", ["N/A", "n/a", "none", "Unknown", "not specified", "-", "TBD", "  "]
)
def test_placeholders_are_junk(value):
    assert is_junk(value)
    assert clean_str(value, max_chars=50) == ""


def test_real_values_are_not_junk():
    assert not is_junk("industrial robots")
    assert clean_str("  **Globex**  ", max_chars=50) == "Globex"
    assert clean_str("a\n  multi   line   name", max_chars=50) == "a multi line name"


def test_non_strings_become_empty():
    # A model that answers {"company": 42} must not poison every later step.
    assert clean_str(42, max_chars=50) == ""
    assert clean_values("not a list", max_items=5, max_chars=50) == []


def test_clean_values_dedupes_case_and_diacritic_insensitively():
    values = ["Türk", "turk", "TURK", "Globex"]
    assert clean_values(values, max_items=10, max_chars=50) == ["Türk", "Globex"]


def test_clean_values_caps_items_and_words():
    many = [f"item {i}" for i in range(30)]
    assert len(clean_values(many, max_items=5, max_chars=50)) == 5
    # A sentence pasted into a name-shaped field loses the sentence, not the field.
    values = ["robots", "this is an entire sentence about our proud heritage"]
    assert clean_values(values, max_items=5, max_chars=80, max_words=3) == ["robots"]
