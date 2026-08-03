"""Fixed, versioned checker prompt set (P5.2): 12 category questions, no LLM.

The public checker asks the same visibility question the MVP crawl does — "when
people ask an AI engine about this *category*, does this brand come up?" — but it
starts from a brand + category a visitor typed, not a crawled site. So unlike
``prompts.generate_prompts`` (which templates a variable ``PROMPT_COUNT`` from a
rich, crawl-derived KYC), this module emits a **fixed set of exactly 12** prompts
in a **stable order**, stamped with :data:`VERSION`. A given KYC therefore always
yields byte-identical prompts, so repeat runs and the 24h result cache stay
consistent and the set is auditable and diffable.

Design choices:

* The 12 questions probe the *category* and never name the brand. That is the
  whole point of the checker: we measure whether the brand shows up *unprompted*
  when a user asks about the category, so the brand is searched for in the
  *answers* by ``footprint.detect``, never planted in the questions.
* Every question is built from KYC fields (topic, location, competitor), so a
  real crawl-KYC yields natural, on-topic questions while a sparse KYC still
  produces 12 non-empty, unique prompts via deterministic fallbacks
  (``"solutions"`` / ``"worldwide"`` / ``"the market leaders"``).
* The set is keyed by ``lang``. English is wired here; Turkish arrives in P5.8.
  An unrecognised ``lang`` deliberately falls back to the English set — a legal
  API input (``lang='tr'`` is accepted by the checker today) must never fail the
  job. See :func:`generate`.
"""

from __future__ import annotations

from app.pipeline.prompts import PromptSpec, topic_pool
from app.pipeline.sanitize import clean_values

# Bump when the wording or ordering of any wired set changes, so cached results
# and stored prompts remain traceable to the generator that produced them.
#
# NOT bumped when the *substituted values* improve: the 12 templates below are
# byte-identical to checker-en-v1, and `checker_methodology.json` is generated
# from an empty KYC (every source empty -> the neutral fallbacks), so a better
# topic on a live run is per-run data, not a new template set.
VERSION = "checker-en-v1"

# Longest phrase (in words) allowed as the category topic; a longer keyword is a
# sentence fragment, not a category, and reads badly stuffed into every slot.
_MAX_TOPIC_WORDS = 6


def _clean(values) -> list[str]:
    """Trimmed, de-duplicated, junk-free list of non-empty strings."""
    return clean_values(values, max_items=25, max_chars=120)


def _primary_topic(kyc) -> str:
    """The single category subject every question is asked about.

    Shares ``prompts.topic_pool``, so the checker gets the same confidence order
    (``category`` -> ``use_cases`` -> filtered keywords -> services -> industry)
    and the same category filter that keeps spec attributes ("payload capacity")
    out of a slot that is repeated across all 12 questions. Falls back to a
    generic noun so the slot is never empty.
    """
    pool = topic_pool(kyc, max_words=_MAX_TOPIC_WORDS)
    return pool[0].text if pool else "solutions"


def _location_phrase(kyc) -> str:
    locations = _clean(kyc.locations)
    return f"in {locations[0]}" if locations else "worldwide"


def _lead_competitor(kyc) -> str:
    competitors = _clean(kyc.competitors)
    return competitors[0] if competitors else "the market leaders"


def _english(kyc) -> list[PromptSpec]:
    """The wired English set: 12 unique, non-empty, category-tagged questions."""
    topic = _primary_topic(kyc)
    loc = _location_phrase(kyc)
    competitor = _lead_competitor(kyc)
    return [
        PromptSpec(f"What are the best {topic} available today?", "recommendation"),
        PromptSpec(f"Which {topic} offer the best value for the money?", "recommendation"),
        PromptSpec(f"Who are the leading {topic} brands {loc}?", "makers"),
        PromptSpec(f"Which companies make the most popular {topic} {loc}?", "makers"),
        PromptSpec(f"How do the top {topic} brands compare?", "comparison"),
        PromptSpec(f"What sets the best {topic} providers apart from the rest?", "comparison"),
        PromptSpec(f"What are good alternatives to {competitor} for {topic}?", "alternatives"),
        PromptSpec(
            f"Besides {competitor}, which brands are worth considering for {topic}?",
            "alternatives",
        ),
        PromptSpec(f"Which brands are known for the best {topic} {loc}?", "best-of"),
        PromptSpec(f"What is the most trusted name in {topic} right now?", "best-of"),
        PromptSpec(f"Which {topic} would you recommend for everyday use, and why?", "use-case"),
        PromptSpec(
            f"If someone is shopping for {topic}, which brands should they look at first?",
            "use-case",
        ),
    ]


# Wired language sets. Turkish ('tr') is added in P5.8; until then an unknown
# lang falls back to English rather than failing an otherwise-legal submit.
_SETS = {"en": _english}


def generate(kyc, lang: str = "en") -> list[PromptSpec]:
    """Return the fixed 12-prompt set for ``lang`` (English fallback).

    ``kyc`` is a ``pipeline.kyc.KYC``; ``lang`` is the analysis language. The
    result is a list of exactly 12 unique, non-empty :class:`PromptSpec` values
    in a stable order (see :data:`VERSION`).
    """
    builder = _SETS.get((lang or "en").strip().casefold(), _english)
    return builder(kyc)
