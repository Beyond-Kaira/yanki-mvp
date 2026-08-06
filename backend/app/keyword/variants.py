"""Local query variants from a seed — no network.

Shapes mirror ``serp_visibility`` keyword-shaped queries: what people type into
a search box around a topic, not full assistant questions.
"""

from __future__ import annotations

from app.keyword.normalize import collapse_keyword_whitespace, is_usable_phrase

# Cycled shapes; seed itself is added separately as source="seed".
_SEED_QUERY_VARIANT_SHAPES = (
    "best {seed}",
    "top {seed} companies",
    "{seed} comparison",
    "{seed} reviews",
    "{seed} alternatives",
    "how to choose {seed}",
    "{seed} for business",
    "cheap {seed}",
)


def build_seed_query_variants(seed: str, *, limit: int = 12) -> list[str]:
    """Return deduped search-box variants derived only from ``seed``."""
    cleaned = collapse_keyword_whitespace(seed)
    if not cleaned or limit <= 0:
        return []
    out: list[str] = []
    seen: set[str] = {cleaned.lower()}
    for shape in _SEED_QUERY_VARIANT_SHAPES:
        if len(out) >= limit:
            break
        phrase = collapse_keyword_whitespace(shape.format(seed=cleaned))
        key = phrase.lower()
        if not is_usable_phrase(phrase) or key in seen:
            continue
        seen.add(key)
        out.append(phrase)
    return out
