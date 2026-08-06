"""Read-time aggregation of a checker analysis's stored rows (P5.3).

The public checker promises two results the MVP crawl never surfaced: an
**engine-by-engine presence map** ("who showed up where") and the list of
**competitor brands that appeared** in the LLM answers. Both compose entirely
from rows the pipeline already writes — the ``responses`` table's ``footprint``
booleans and ``raw_text`` — so we compute them at read time in this pure helper
instead of adding a column, a pipeline step, or (crucially) an LLM call. The
whole thing is deterministic and costs **$0**.

Two aggregates, one pass:

* **engine_presence** — group the responses by ``engine`` and report, per
  engine, how many answers mentioned the company (``footprint is True``) out of
  the total answers for that engine. The per-engine totals sum to the analysis'
  ``total_responses`` and the per-engine ``mentioned`` counts sum to its
  ``footprint_count``, so the map is always consistent with the headline score.

* **competitors_appeared** — a deterministic **proper-noun co-mention
  heuristic** over the raw answers. We scan each answer for Title-Case brand
  names, **exclude** the searched company + its ``aliases`` (case-insensitively)
  and a small EN/TR stoplist of sentence-starters / connectives, count how many
  distinct answers each surviving name appears in, and return the top
  :data:`TOP_N` by that count. This deliberately does **not** intersect against
  ``kyc.competitors`` — that list is whatever the KYC step happened to name and
  would miss brands the answers actually surfaced. It captures "brands that
  showed up" faithfully, from the answers alone.

Heuristic design notes (why this is more than a naive Title-Case grep):

* **Adjacent-token grouping.** Consecutive capitalized words separated only by
  spaces are grouped into one name, so a multi-word brand like ``Yanki Demo Co``
  is treated (and excluded) as a whole — no ``Demo Co`` fragment leaks through.
  Any punctuation (comma, period, ...) between two capitalized words breaks the
  run, so ``Acme, Globex`` stays two names and a sentence boundary
  (``... Co. Other ...``) never welds two names together.
* **Stoplist.** LLM answers capitalize the first word of every sentence, so
  ``For``, ``Some``, ``Other`` (and Turkish equivalents) would masquerade as
  brands. The stoplist drops them; leading/trailing stoplist words are also
  stripped from a group (``The Acme`` -> ``Acme``). Recommendation/imperative
  verbs (``Try``, ``Choose``, ``Visit`` ...) are in the list too, so a verb that
  welds onto a following brand (``Try Acme``, ``Choose Nike``) is stripped —
  leaving the real brand, and letting its exclusion apply. It is a curated
  heuristic, not exhaustive — a real brand spelled exactly like a stopword
  (rare) would be dropped; acceptable at $0.
* **Ambiguous particle guard.** A few stoplist entries are short Turkish
  function words that also begin English brand names (``De`` Beers, ``Ben``
  Sherman, ``En`` Route). We never strip such a word from the FRONT of a
  multi-word name, so those brands keep their first token — while the same word
  standing alone (a bare TR sentence-lead) is still dropped.
* **Case-insensitive, possessive-tolerant exclusion.** The searched brand is
  stored casefolded while answers use Title-Case, so all exclusion comparisons
  casefold both sides. An answer about the brand routinely writes it possessive
  (``Nike's new line ...``), so a trailing English possessive is stripped for
  the comparison only — never from a reported name, so a competitor that
  genuinely ends in ``'s`` (``McDonald's``) keeps its name.

The helper is intentionally free of any ORM / API import: it consumes a plain
sequence of duck-typed response rows (``engine`` / ``footprint`` / ``raw_text``)
plus the ``kyc`` dict, and returns plain frozen dataclasses. The route
(``_to_out``) maps those onto the Pydantic contract models, and only for
``kind='checker'`` rows — MVP analyses carry ``null`` for both fields.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

# How many competitor names to return, ranked by how many answers name them.
# Ten is comfortably more than a checker results card shows and keeps a long
# tail of one-off proper nouns out of the payload.
TOP_N = 10

# A candidate name must be at least this long to count (drops stray single
# capitals like a lone "I" that the grouping would otherwise surface).
_MIN_NAME_LEN = 2

# Turkish-aware letter classes. "First letter uppercase" starts a name; the rest
# of a word may be any letter (so acronyms like "IBM" and inner caps like
# "McKinsey" stay whole) plus the intra-name punctuation brands use ("&", "'",
# "-", e.g. "P&G", "L'Oreal", "Coca-Cola"). A "." is deliberately NOT a name
# character, so a sentence-final "Co." ends the run before the next sentence.
_UPPER = "A-ZÇĞİÖŞÜ"
_LETTER = "A-Za-zÇĞİÖŞÜçğıöşü"
_WORD = rf"[{_UPPER}][{_LETTER}&'’-]*"
# One name = a capitalized word, then zero+ more capitalized words joined by
# spaces/tabs only. Punctuation between words breaks the run (see module doc).
_NAME_RE = re.compile(rf"{_WORD}(?:[ \t]+{_WORD})*")

# Sentence-starters, pronouns, connectives and generic list words that LLM
# answers routinely Title-Case. Casefolded for comparison. English + Turkish
# (the checker is bilingual; TR copy lands in a later card, but real TR answers
# can already appear). Not exhaustive — a heuristic tuned for co-mention noise.
_STOPWORDS_RAW = [
    # English
    "the", "a", "an", "and", "or", "but", "so", "as", "if", "then", "than",
    "this", "that", "these", "those", "it", "its", "we", "you", "they", "he",
    "she", "i", "there", "here", "when", "where", "what", "which", "who", "whom",
    "whose", "why", "how", "in", "on", "at", "to", "of", "for", "with", "from",
    "by", "about", "into", "over", "under", "some", "any", "many", "much",
    "most", "more", "other", "others", "another", "both", "each", "every",
    "all", "few", "several", "well", "also", "however", "overall", "generally",
    "typically", "based", "depending", "consider", "considering", "note",
    "please", "options", "option", "example", "examples", "etc", "meanwhile",
    "additionally", "furthermore", "moreover", "similarly", "alternatively",
    "yes", "no", "maybe", "best", "top", "popular", "known", "recommend",
    "recommended", "include", "includes", "including",
    # Recommendation / imperative verbs an LLM Title-Cases at a sentence start,
    # welding onto the following brand ("Try Acme", "Choose Nike over ..."). As
    # leading tokens they are stripped, so the real brand (and its exclusion)
    # survives instead of a bogus "Try Acme" / "Choose Nike" name.
    "try", "visit", "choose", "explore", "discover", "compare", "suggest",
    "suggests", "prefer", "avoid",
    # Turkish (both plain and İ-initial spellings so casefold matches either way)
    "bir", "ve", "veya", "ya", "ama", "fakat", "ancak", "çünkü", "ki", "da",
    "de", "bu", "şu", "o", "bunlar", "şunlar", "onlar", "ben", "sen", "biz",
    "siz", "için", "İçin", "ile", "İle", "ise", "İse", "gibi", "kadar", "daha",
    "çok", "az", "bazı", "birçok", "diğer", "başka", "her", "hepsi", "tüm",
    "bütün", "ayrıca", "örneğin", "genellikle", "genel", "olarak", "yani",
    "hem", "ne", "nasıl", "neden", "niçin", "hangi", "kim", "nerede", "evet",
    "hayır", "belki", "en", "iyi", "İyi", "popüler", "seçenek", "seçenekler",
    "öneri", "öneriler", "öneririm",
]
_STOPWORDS = frozenset(w.casefold() for w in _STOPWORDS_RAW)

# A handful of stoplist words are short Turkish function words that double as
# English proper-name particles ("De" Beers, "Ben" Sherman, "En" Route, "Az"
# Kaban). We still drop them when they STAND ALONE (a bare TR sentence-starter),
# but never strip one from the FRONT of a multi-word name, so those real brands
# keep their first token. Casefolded for comparison.
_AMBIGUOUS_LEADING = frozenset({"de", "en", "o", "az", "ben"})

# Trailing English possessive ("'s"/"’s", or a lone apostrophe on a plural like
# "Companies'"). Stripped only for the exclusion COMPARISON — never from the
# reported name — so an answer about the searched brand written in the
# possessive ("Nike's new line ...") still matches its bare alias and is
# excluded, while a competitor that genuinely ends in "'s" ("McDonald's") keeps
# its name and is still reported.
_POSSESSIVE_RE = re.compile(r"['’]s?$")


class ResponseLike(Protocol):
    """The duck-typed shape this helper reads off each response row."""

    engine: str
    footprint: bool | None
    raw_text: str


@dataclass(frozen=True)
class EnginePresenceStat:
    """One engine's presence: ``mentioned`` of ``total`` answers named the brand."""

    engine: str
    mentioned: int
    total: int


@dataclass(frozen=True)
class CompetitorStat:
    """A competitor brand and the number of answers it co-appeared in."""

    name: str
    mentions: int


@dataclass(frozen=True)
class CheckerSummary:
    """The two checker-only read-time aggregates."""

    engine_presence: list[EnginePresenceStat] = field(default_factory=list)
    competitors_appeared: list[CompetitorStat] = field(default_factory=list)


def brand_exclusions(kyc: dict[str, Any] | None) -> set[str]:
    """Casefolded names to never report: the searched company + its aliases."""
    excluded: set[str] = set()
    if not kyc:
        return excluded
    company = kyc.get("company")
    if isinstance(company, str) and company.strip():
        excluded.add(company.strip().casefold())
    aliases = kyc.get("aliases")
    if isinstance(aliases, list):
        for alias in aliases:
            if isinstance(alias, str) and alias.strip():
                excluded.add(alias.strip().casefold())
    return excluded


def _is_excluded(name: str, excluded: set[str]) -> bool:
    """True if the candidate is the searched brand — bare or possessive form.

    The exclusion set holds casefolded bare names. An answer about the brand
    routinely uses its possessive ("Nike's new line ..."), whose casefold never
    equals the bare alias, so we also test the name with a trailing English
    possessive removed. The strip is for the comparison only, never for the
    reported name.
    """
    folded = name.casefold()
    if folded in excluded:
        return True
    bare = _POSSESSIVE_RE.sub("", folded)
    return bare != folded and bare in excluded


def _clean_group(raw: str) -> str | None:
    """Trim leading/trailing stopwords from a capitalized run; None if nothing left."""
    tokens = raw.split()
    # Trailing stopwords always strip ("Acme And" -> "Acme").
    while tokens and tokens[-1].casefold() in _STOPWORDS:
        tokens = tokens[:-1]
    # Leading stopwords strip too ("The Acme" -> "Acme"), EXCEPT a short
    # ambiguous particle at the front of a multi-word name — that is a real
    # brand's first token ("De Beers"), not a sentence lead, so we keep it. The
    # particle is still dropped when it stands alone (guard is multi-token only).
    while tokens and tokens[0].casefold() in _STOPWORDS:
        if len(tokens) > 1 and tokens[0].casefold() in _AMBIGUOUS_LEADING:
            break
        tokens = tokens[1:]
    if not tokens:
        return None
    name = " ".join(tokens)
    if len(name) < _MIN_NAME_LEN:
        return None
    return name


def names_in_answer(raw_text: str, excluded: set[str]) -> set[str]:
    """Distinct competitor-candidate names in one answer (post-exclusion)."""
    found: set[str] = set()
    for match in _NAME_RE.finditer(raw_text or ""):
        name = _clean_group(match.group(0))
        if name is None:
            continue
        if _is_excluded(name, excluded):
            continue
        found.add(name)
    return found


def _engine_presence(responses: list[ResponseLike]) -> list[EnginePresenceStat]:
    """Per-engine mentioned/total, in first-seen (panel) order.

    ``total`` counts every response for the engine; ``mentioned`` counts those
    whose ``footprint`` is True (``None``/False do not count as a mention). The
    totals sum to ``len(responses)`` and the mentions to the footprint count, so
    the map stays consistent with ``total_responses`` / ``footprint_count``.
    """
    totals: dict[str, int] = {}
    mentioned: dict[str, int] = {}
    for response in responses:
        engine = response.engine
        totals[engine] = totals.get(engine, 0) + 1
        if response.footprint:
            mentioned[engine] = mentioned.get(engine, 0) + 1
    return [
        EnginePresenceStat(engine=engine, mentioned=mentioned.get(engine, 0), total=total)
        for engine, total in totals.items()
    ]


def _competitors_appeared(
    responses: list[ResponseLike], excluded: set[str]
) -> list[CompetitorStat]:
    """Top proper-noun co-mentions across answers, ranked by answer count.

    Each name is counted once per answer it appears in (so a verbose answer that
    repeats a brand cannot dominate). Ties break alphabetically on the casefolded
    name for a stable, deterministic order.
    """
    counts: Counter[str] = Counter()
    display: dict[str, str] = {}
    for response in responses:
        for name in names_in_answer(response.raw_text, excluded):
            key = name.casefold()
            counts[key] += 1
            display.setdefault(key, name)
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [CompetitorStat(name=display[key], mentions=count) for key, count in ranked[:TOP_N]]


def summarize_checker(
    responses: Sequence[ResponseLike], kyc: dict[str, Any] | None
) -> CheckerSummary:
    """Compute the engine-presence map and competitor co-mentions for a checker run.

    Pure and deterministic: given the same responses + kyc it always returns the
    same summary, makes no I/O and no LLM call. ``responses`` may be empty (a
    still-running or empty analysis) — both aggregates come back empty.
    """
    rows = list(responses)
    excluded = brand_exclusions(kyc)
    return CheckerSummary(
        engine_presence=_engine_presence(rows),
        competitors_appeared=_competitors_appeared(rows, excluded),
    )
