"""Local query variants from a seed — no network.

Shapes mirror ``serp_visibility`` keyword-shaped queries: what people type into
a search box around a topic, not full assistant questions.

Smart-skip: drop shapes that would double a leading / trailing token already in
the seed (``best best…``), skip tiny seeds, and skip English templates when the
seed has non-basic-Latin letters.
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

# Below this length, local templates are more noise than signal.
_MIN_VARIANT_SEED_CHARS = 3


def _seed_suits_english_templates(seed: str) -> bool:
    """False when any letter is outside basic Latin a–z (EN shapes would be junk)."""
    has_letter = False
    for char in seed:
        if not char.isalpha():
            continue
        has_letter = True
        lowered = char.lower()
        if len(lowered) != 1 or not ("a" <= lowered <= "z"):
            return False
    return has_letter


def _shape_conflicts_with_seed(shape: str, seed: str) -> bool:
    """True when applying ``shape`` would repeat seed edge tokens."""
    if "{seed}" not in shape:
        return True
    before, after = shape.split("{seed}", 1)
    seed_tokens = seed.lower().split()
    before_tokens = before.strip().lower().split()
    after_tokens = after.strip().lower().split()
    if before_tokens and seed_tokens[: len(before_tokens)] == before_tokens:
        return True
    if after_tokens and seed_tokens[-len(after_tokens) :] == after_tokens:
        return True
    return False


def _has_adjacent_duplicate_tokens(phrase: str) -> bool:
    tokens = phrase.lower().split()
    return any(a == b for a, b in zip(tokens, tokens[1:], strict=False))


def build_seed_query_variants(seed: str, *, limit: int = 12) -> list[str]:
    """Return deduped search-box variants derived only from ``seed``."""
    cleaned = collapse_keyword_whitespace(seed)
    if not cleaned or limit <= 0:
        return []
    if len(cleaned) < _MIN_VARIANT_SEED_CHARS:
        return []
    if not _seed_suits_english_templates(cleaned):
        return []

    out: list[str] = []
    seen: set[str] = {cleaned.lower()}
    for shape in _SEED_QUERY_VARIANT_SHAPES:
        if len(out) >= limit:
            break
        if _shape_conflicts_with_seed(shape, cleaned):
            continue
        phrase = collapse_keyword_whitespace(shape.format(seed=cleaned))
        key = phrase.lower()
        if not is_usable_phrase(phrase) or key in seen:
            continue
        if _has_adjacent_duplicate_tokens(phrase):
            continue
        seen.add(key)
        out.append(phrase)
    return out
