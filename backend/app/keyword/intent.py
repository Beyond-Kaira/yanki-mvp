"""Rule-based search-intent labels for keyword-expand preview rows.

Not vendor intent. Used only until a licensed or model-backed classifier lands.
See ``docs/keyword-preview-oss.md`` (Estimated honesty + debt notes).

**Debt / leak risk:** marker tuples below are hardcoded English token lists.
They mis-label non-English seeds, miss synonyms, and can be reverse-engineered
from the UI as “our intent model”. Do not present as Product-grade intent.
Tracked for cleanup in ``docs/keyword-preview-to-product-engineering.md``.
"""

from __future__ import annotations

from app.keyword.normalize import collapse_keyword_whitespace

# Returned strings match common SEO intent vocabulary so the UI can reuse copy.
INTENT_INFORMATIONAL = "informational"
INTENT_NAVIGATIONAL = "navigational"
INTENT_COMMERCIAL = "commercial"
INTENT_TRANSACTIONAL = "transactional"

# NOTE: hardcoded EN markers — see module docstring (leak / i18n debt).
_TRANSACTIONAL_MARKERS = (
    "buy",
    "price",
    "pricing",
    "cost",
    "cheap",
    "deal",
    "coupon",
    "discount",
    "order",
)
_COMMERCIAL_MARKERS = (
    "best",
    "vs",
    "versus",
    "comparison",
    "compare",
    "alternative",
    "alternatives",
    "review",
    "reviews",
    "top ",
)
_INFORMATIONAL_MARKERS = (
    "how to",
    "how ",
    "what ",
    "why ",
    "when ",
    "where ",
    "who ",
    "is ",
    "can ",
    "does ",
    "guide",
    "tutorial",
)


def classify_keyword_search_intent(phrase: str) -> str:
    """Return one intent label for a keyword phrase (rule heuristic).

    Fallback is always ``informational`` when no marker matches (or input is
    empty). That is deliberate for Preview — unknown ≠ navigational/commercial
    — but it will over-tag bland head terms as informational.
    """
    text = collapse_keyword_whitespace(phrase).lower()
    if not text:
        return INTENT_INFORMATIONAL
    if " login" in f" {text}" or text.endswith(" login"):
        return INTENT_NAVIGATIONAL
    if any(marker in text for marker in _TRANSACTIONAL_MARKERS):
        return INTENT_TRANSACTIONAL
    if any(marker in text for marker in _COMMERCIAL_MARKERS):
        return INTENT_COMMERCIAL
    if any(marker in text for marker in _INFORMATIONAL_MARKERS):
        return INTENT_INFORMATIONAL
    return INTENT_INFORMATIONAL
