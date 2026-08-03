from __future__ import annotations

import pytest

from app.pipeline.textfold import fold, fold_ascii


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Türk", "Turk"),
        ("TÜRK", "TURK"),
        ("İşbank", "Isbank"),
        ("ürünler", "urunler"),
        ("Nestlé", "Nestle"),
        ("Škoda", "Skoda"),
        ("Citroën", "Citroen"),
        ("Müller", "Muller"),
        ("plain ascii", "plain ascii"),
    ],
)
def test_fold_ascii_replaces_diacritics(text, expected):
    assert fold_ascii(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "İşbank",
        "TÜRK Holding çğıöşü ÇĞİÖŞÜ",
        "Nestlé Škoda Citroën Løvens",
        "",
        "no diacritics at all",
    ],
)
def test_fold_ascii_is_length_preserving(text):
    # footprint.detect matches on folded text and slices the ORIGINAL by index,
    # so any entry that changed length would silently corrupt every snippet.
    assert len(fold_ascii(text)) == len(text)


def test_eszett_is_left_alone():
    # "ß" -> "ss" would break the length invariant, so it stays unfolded.
    assert fold_ascii("Straße") == "Straße"


def test_fold_adds_case_folding_without_splitting_dotted_i():
    # casefold() alone turns "İ" into two codepoints (i + U+0307); folding first
    # avoids that.
    assert fold("İŞBANK") == "isbank"
    assert fold("Ürünler") == "urunler"
