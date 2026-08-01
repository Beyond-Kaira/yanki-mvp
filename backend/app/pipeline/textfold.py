"""ASCII diacritic folding, shared by discovery and footprint matching.

Two callers need the same map, so it lives here once rather than drifting into
two copies:

* ``footprint.detect`` matches terms against a folded answer but reports the
  matched snippet by slicing the **original** text. That makes
  length-preservation a correctness requirement, not a nicety: every entry maps
  exactly one character to exactly one character, so a match index in the folded
  text still points at the same place in the original.
* ``discovery`` only compares, so it layers ``casefold()`` on top via ``fold``.

Why not just ``casefold()``? Because it is not length-preserving. Turkish dotted
capital ``İ`` casefolds to **two** codepoints (``i`` + U+0307 combining dot
above), which would silently shift every snippet after it — and would also stop
``İşbank`` from matching the alias ``Isbank`` at all. Folding first, with a 1:1
table, fixes both.

For the same reason German ``ß`` is deliberately absent: it expands to ``ss``.
It stays unfolded rather than breaking the invariant the whole module rests on.
"""

from __future__ import annotations

# Case-preserving so the table stays 1:1 — callers that want case-insensitivity
# use ``re.IGNORECASE`` or ``fold`` instead of losing the length guarantee.
_ASCII_FOLD_PAIRS = {
    # Turkish
    "ç": "c",
    "ğ": "g",
    "ı": "i",
    "İ": "I",
    "ö": "o",
    "ş": "s",
    "ü": "u",
    "â": "a",
    "î": "i",
    "û": "u",
    # Other Latin-script brand names we routinely meet (Nestlé, Müller, Škoda,
    # Citroën, Nutriça, Løvens, ...).
    "á": "a",
    "à": "a",
    "ä": "a",
    "å": "a",
    "ã": "a",
    "é": "e",
    "è": "e",
    "ê": "e",
    "ë": "e",
    "í": "i",
    "ì": "i",
    "ï": "i",
    "ó": "o",
    "ò": "o",
    "ô": "o",
    "õ": "o",
    "ø": "o",
    "ú": "u",
    "ù": "u",
    "ñ": "n",
    "ý": "y",
    "ÿ": "y",
    "č": "c",
    "ć": "c",
    "š": "s",
    "ž": "z",
    "ł": "l",
    "đ": "d",
    "ř": "r",
    "ň": "n",
    "ě": "e",
    "ů": "u",
}

# Add the uppercase partner of every entry (skipping any whose upper() is not a
# single character, which would break the 1:1 invariant). "İ" is already listed
# explicitly because "i".upper() is "I", never "İ".
_ASCII_FOLD = {}
for _lower, _ascii in _ASCII_FOLD_PAIRS.items():
    _ASCII_FOLD[_lower] = _ascii
    _upper = _lower.upper()
    if len(_upper) == 1 and _upper != _lower:
        _ASCII_FOLD.setdefault(_upper, _ascii.upper())

_TABLE = str.maketrans(_ASCII_FOLD)


def fold_ascii(text: str) -> str:
    """Replace Latin diacritics with their ASCII base letter, preserving case.

    Length-preserving: ``len(fold_ascii(t)) == len(t)`` for every ``t``.
    """
    return text.translate(_TABLE)


def fold(text: str) -> str:
    """``fold_ascii`` plus case folding, for callers that only ever compare.

    Folds *before* casefolding so ``"İ"`` becomes ``"i"`` rather than the
    two-codepoint ``"i" + U+0307`` that ``casefold()`` alone produces.
    """
    return fold_ascii(text).casefold()
