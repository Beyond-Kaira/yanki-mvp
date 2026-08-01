"""Value hygiene shared by KYC extraction and prompt generation.

Whatever JSON the model returns is what we persist, what prompts are built from,
and what ``footprint`` counts as a mention. So every value gets one pass through
here first: trimmed, unwrapped, junk-filtered, de-duplicated and capped.

The other thing this module owns is the **normalized key** — one folded,
case-insensitive, punctuation-free form of a string, used for three jobs that
must agree with each other:

* de-duplicating values that differ only in case, diacritics or punctuation
  (``Coca-Cola`` / ``coca cola``);
* deciding whether a name the model returned actually appears in the crawled
  text (:func:`contains`, the grounding check in ``kyc``);
* deciding whether a generated prompt leaks the brand it is meant to measure
  (``prompts``).

The key deliberately reuses ``textfold.fold``, the same folding ``footprint``
matches with, so a name the site writes ``Türk`` and the model writes ``Turk``
is one value in all three places.
"""

from __future__ import annotations

import re

from app.pipeline.textfold import fold

# Placeholders a model reaches for instead of leaving a field empty. Compared
# against the normalized key, so "N/A.", "n / a" and "N.A" all collapse here.
_JUNK_KEYS = frozenset(
    {
        "",
        "n a",
        "na",
        "none",
        "null",
        "nil",
        "nan",
        "unknown",
        "unspecified",
        "not specified",
        "not available",
        "not applicable",
        "not mentioned",
        "no data",
        "tbd",
        "todo",
        "various",
        "other",
        "others",
        "etc",
    }
)

# Quotes and markdown emphasis a model wraps a value in ("**Globex**").
_WRAPPERS = "\"'“”‘’`*_ \t\r\n"

_WHITESPACE = re.compile(r"\s+")
# Everything that is not a letter or digit becomes a separator in the key, so
# punctuation, hyphens and underscores never distinguish two spellings.
_NON_ALNUM = re.compile(r"[\W_]+", re.UNICODE)


def normalize_key(value: str) -> str:
    """The comparison form of a string: folded, casefolded, punctuation-free.

    ``"Coca-Cola A.Ş."`` and ``"coca cola a.s"`` both key to ``"coca cola a s"``.
    Used for dedupe, for grounding containment and for brand-leak detection —
    one identity, so those three never disagree.
    """
    return _NON_ALNUM.sub(" ", fold(value or "")).strip()


def contains(haystack_key: str, value: str) -> bool:
    """True when ``value`` appears in an already-normalized ``haystack_key``.

    Both sides are padded with spaces before the substring test, so the match is
    on whole words: ``"GE"`` does not ground itself inside ``"general"``. An
    empty value never grounds (there is nothing to find).
    """
    needle = normalize_key(value)
    if not needle:
        return False
    return f" {needle} " in f" {haystack_key} "


def is_junk(value: str) -> bool:
    """True for a placeholder value that carries no information."""
    return normalize_key(value) in _JUNK_KEYS


def clean_str(value: object, *, max_chars: int) -> str:
    """Trim, unwrap, collapse whitespace and cap one scalar field.

    Non-strings (a model that answered ``{"company": 42}``) and junk
    placeholders both become ``""`` — a field we know nothing about is better
    empty than confidently wrong, and ``require_usable`` can then see it.
    """
    if not isinstance(value, str):
        return ""
    cleaned = _WHITESPACE.sub(" ", value).strip().strip(_WRAPPERS).strip()
    if not cleaned or is_junk(cleaned):
        return ""
    return cleaned[:max_chars].strip()


def clean_values(
    values: object,
    *,
    max_items: int,
    max_chars: int,
    max_words: int = 0,
) -> list[str]:
    """Clean, junk-filter, de-duplicate and cap one list field.

    Order is first-seen and the surviving spelling is the original one — only
    the *comparison* is normalized. ``max_words`` (0 = unbounded) drops entries
    that are sentences rather than names: a model that pastes a paragraph into
    ``keywords`` should lose the paragraph, not the field.
    """
    if not isinstance(values, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = clean_str(value, max_chars=max_chars)
        if not cleaned:
            continue
        if max_words and len(cleaned.split()) > max_words:
            continue
        key = normalize_key(cleaned)
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
        if len(out) >= max_items:
            break
    return out
