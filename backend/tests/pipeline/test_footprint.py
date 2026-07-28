from __future__ import annotations

import pytest

from app.pipeline.footprint import detect
from app.pipeline.kyc import KYC


def test_footprint_true_with_matched_snippet_when_brand_present(sample_kyc):
    text = "When it comes to warehouse robots, Acme Robotics is a strong option."
    hit, snippet = detect(text, sample_kyc)
    assert hit is True
    assert snippet is not None
    assert "Acme Robotics" in snippet


def test_footprint_false_and_null_snippet_when_absent(sample_kyc):
    hit, snippet = detect("There are many robotics vendors to consider.", sample_kyc)
    assert hit is False
    assert snippet is None


def test_footprint_is_case_insensitive(sample_kyc):
    hit, snippet = detect("we love ACME ROBOTICS here", sample_kyc)
    assert hit is True
    assert snippet is not None


def test_footprint_matches_on_alias(sample_kyc):
    hit, _ = detect("Acme makes great arms.", sample_kyc)
    assert hit is True


def test_footprint_matches_on_domain_alias(sample_kyc):
    hit, _ = detect("Read more at acmerobotics for details.", sample_kyc)
    assert hit is True


def test_footprint_snippet_is_bounded(sample_kyc):
    text = ("x" * 500) + " Acme Robotics " + ("y" * 500)
    hit, snippet = detect(text, sample_kyc)
    assert hit is True
    # +-60 chars of context around a 13-char match -> at most ~133 chars.
    assert len(snippet) <= 60 + len("Acme Robotics") + 60


def test_footprint_is_deterministic(sample_kyc):
    text = "Acme Robotics and also Acme show up twice here."
    first = detect(text, sample_kyc)
    second = detect(text, sample_kyc)
    assert first == second


def test_footprint_empty_text_is_false(sample_kyc):
    assert detect("", sample_kyc) == (False, None)


def test_short_alias_does_not_match_inside_a_longer_word():
    # A short domain-suffix alias like "co" must NOT match inside "compare" /
    # "companies" / "recommend" — word boundaries, not raw substrings.
    kyc = KYC(company="Globex", aliases=["Globex", "co"])
    text = "How do the leading providers compare? I would recommend several companies."
    hit, snippet = detect(text, kyc)
    assert hit is False
    assert snippet is None


def test_two_letter_brand_matches_only_as_a_whole_word():
    kyc = KYC(company="GE", aliases=["GE"])
    # "general" / "large" must not count as a GE footprint...
    assert detect("A general contractor handling large jobs.", kyc) == (False, None)
    # ...but a standalone mention still does.
    hit, _ = detect("For appliances, GE is a solid pick.", kyc)
    assert hit is True


# The measured gap table from docs/discovery-kyc-improvements.md step 2, one
# case per row. Row 1 (plain case folding) already worked before this change;
# it is kept as a regression guard.
@pytest.mark.parametrize(
    ("answer", "term"),
    [
        ("I would pick TÜRK Holding for that.", "Türk"),  # case only (already worked)
        ("I would pick TÜRK Holding for that.", "Turk"),  # diacritics folded
        ("Try İşbank for corporate accounts.", "Isbank"),  # Turkish dotted İ
        ("Everyone drinks Coca Cola here.", "Coca-Cola"),  # hyphen -> space
        ("Everyone drinks Coca-Cola here.", "Coca Cola"),  # space -> hyphen
        ("Nestle is the obvious comparison.", "Nestlé"),  # folded alias, plain text
        ("Nestlé is the obvious comparison.", "Nestle"),  # folded text, plain alias
        ("The T Mobile plan is cheaper.", "T-Mobile"),  # short hyphenated brand
    ],
)
def test_brand_forms_that_should_match(answer, term):
    hit, snippet = detect(answer, KYC(company=term, aliases=[term]))
    assert hit is True
    assert snippet is not None


def test_snippet_keeps_the_original_spelling_after_folding():
    # Matching happens on folded text, but the snippet is sliced from the real
    # answer — a length-preserving fold is what keeps that index honest.
    answer = "Analysts rate İşbank and TÜRK Holding highly this quarter."
    hit, snippet = detect(answer, KYC(company="Isbank", aliases=["Isbank"]))
    assert hit is True
    assert "İşbank" in snippet  # diacritics intact, not the folded form


def test_folding_does_not_widen_short_brands_into_false_positives():
    # A 2-char brand stays anchored on word boundaries even with the new
    # tolerances: no substring hits, and no hyphen/space bridge across words.
    kyc = KYC(company="GE", aliases=["GE", "Co"])
    text = "General Electric and large German companies compare well here."
    assert detect(text, kyc) == (False, None)


def test_separator_tolerance_does_not_bridge_unrelated_words():
    # "Coca-Cola" must not match "Coca" and "Cola" merely appearing near each
    # other with other words in between.
    kyc = KYC(company="Coca-Cola", aliases=["Coca-Cola"])
    assert detect("Coca leaves and cola nuts are different things.", kyc) == (
        False,
        None,
    )
