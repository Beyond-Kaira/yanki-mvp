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
MAX_RELATED_IDEA_TOKENS = 8

# Leading tokens that mark a PAA-style question people type into search.
_QUESTION_PREFIXES = frozenset(
    {
        "who",
        "what",
        "whats",
        "when",
        "where",
        "why",
        "how",
        "which",
        "whose",
        "whom",
        "is",
        "are",
        "was",
        "were",
        "do",
        "does",
        "did",
        "can",
        "could",
        "should",
        "would",
        "will",
        "may",
        "might",
    }
)


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
    if len(cleaned) < MIN_KEYWORD_PHRASE_CHARS or len(cleaned) > MAX_KEYWORD_PHRASE_CHARS:
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


def should_exclude_keyword_candidate(phrase: str, brand_exclusion_keys: Sequence[str]) -> bool:
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
    lowered = cleaned.lower()
    if "@" in lowered or ".com" in lowered or ".org" in lowered or ".net" in lowered:
        return False
    return True


def looks_like_paa_idea(text: str) -> bool:
    """True for short question-shaped answers worth keeping as ``paa`` rows."""
    if not looks_like_keyword_idea(text):
        return False
    cleaned = collapse_keyword_whitespace(text)
    if cleaned.endswith("?"):
        return True
    first = cleaned.split()[0].lower().rstrip("?:!,.")
    return first in _QUESTION_PREFIXES


def phrase_covers_seed_tokens(seed: str, phrase: str) -> bool:
    """True when every meaningful seed token appears as a whole token in phrase."""
    seed_tokens = [t for t in keyword_dedupe_key(seed).split() if len(t) >= 2]
    if not seed_tokens:
        seed_tokens = [t for t in keyword_dedupe_key(seed).split() if t]
    if not seed_tokens:
        return False
    phrase_tokens = set(keyword_dedupe_key(phrase).split())
    return all(token in phrase_tokens for token in seed_tokens)


def looks_like_related_keyword_idea(seed: str, phrase: str) -> bool:
    """Title-mined related row: keyword-shaped, covers seed tokens, not a headline dump."""
    if not looks_like_keyword_idea(phrase):
        return False
    cleaned = collapse_keyword_whitespace(phrase)
    if len(cleaned.split()) > MAX_RELATED_IDEA_TOKENS:
        return False
    if keyword_dedupe_key(cleaned) == keyword_dedupe_key(seed):
        return False
    return phrase_covers_seed_tokens(seed, cleaned)
