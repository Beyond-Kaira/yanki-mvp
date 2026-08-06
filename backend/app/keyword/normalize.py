"""Normalize and filter keyword-expand candidates for the OSS preview.

Keeps Magic-table rows free of junk (URLs, tiny fragments, duplicates) and
optional brand names the caller wants excluded — same idea as
``prompts.leaks_brand``, without requiring a full KYC object.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.pipeline.prompts import leaks_brand
from app.pipeline.sanitize import normalize_key

MIN_KEYWORD_PHRASE_CHARS = 2
MAX_KEYWORD_PHRASE_CHARS = 120
MAX_KEYWORD_IDEA_CHARS = 80


def collapse_keyword_whitespace(text: str) -> str:
    """Collapse internal whitespace on a keyword candidate; ``\"\"`` if not a str."""
    if not isinstance(text, str):
        return ""
    return " ".join(text.split()).strip()


def keyword_dedupe_key(text: str) -> str:
    """Casefolded key used to dedupe keyword-expand rows."""
    return normalize_key(collapse_keyword_whitespace(text))


def is_usable_phrase(text: str) -> bool:
    """False for empties, URLs, or phrases outside the keyword length budget."""
    cleaned = collapse_keyword_whitespace(text)
    if (
        len(cleaned) < MIN_KEYWORD_PHRASE_CHARS
        or len(cleaned) > MAX_KEYWORD_PHRASE_CHARS
    ):
        return False
    lowered = cleaned.lower()
    if "://" in lowered or lowered.startswith("www."):
        return False
    return True


def brand_names_to_exclusion_keys(brand_names: Sequence[str] | None) -> list[str]:
    """Turn caller brand strings into keys for ``leaks_brand`` matching."""
    if not brand_names:
        return []
    keys: list[str] = []
    seen: set[str] = set()
    for name in brand_names:
        key = normalize_key(collapse_keyword_whitespace(str(name)))
        if len(key) < 2 or key in seen:
            continue
        seen.add(key)
        keys.append(key)
    return keys


def should_exclude_keyword_candidate(
    phrase: str, brand_exclusion_keys: Sequence[str]
) -> bool:
    """True when a candidate is unusable or names an excluded brand."""
    if not is_usable_phrase(phrase):
        return True
    if brand_exclusion_keys and leaks_brand(phrase, list(brand_exclusion_keys)):
        return True
    return False


def looks_like_keyword_idea(text: str) -> bool:
    """Stricter than ``is_usable_phrase`` — drop prose / trailing sentences.

    Used for PAA-like answers and title-mined related rows so essay snippets do
    not land in the Magic table.
    """
    cleaned = collapse_keyword_whitespace(text)
    if not is_usable_phrase(cleaned):
        return False
    if cleaned.endswith("."):
        return False
    if len(cleaned) > MAX_KEYWORD_IDEA_CHARS:
        return False
    return True
