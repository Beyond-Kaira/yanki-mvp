"""SearXNG-backed keyword expansion (open-source preview path).

One live search for the seed pulls suggestions + answers; title-mined related
phrases and local variants fill the rest — no Semrush DB, politeness budget
of a single SearXNG round-trip per expand (plus the seed itself).

Merge order (after dedupe): seed → suggestion → paa → related → variant.
Variants are last so ``max_ideas`` is not consumed by template filler first.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.keyword.base import KeywordExpandResult, KeywordIdea, KeywordUnavailable
from app.keyword.normalize import (
    brand_names_to_exclusion_keys,
    collapse_keyword_whitespace,
    keyword_dedupe_key,
    looks_like_paa_idea,
    looks_like_related_keyword_idea,
    should_exclude_keyword_candidate,
)
from app.keyword.signals import build_estimated_keyword_idea_signals
from app.keyword.variants import build_seed_query_variants
from app.serp.base import SerpPage, SerpUnavailable
from app.serp.searxng import SearxngSource

# How many result titles to scan for related-looking phrases.
_MAX_RELATED_FROM_TITLES = 15


def _related_keyword_phrases_from_serp_titles(seed: str, page: SerpPage) -> list[str]:
    """Pull short, seed-relevant SERP titles as weak ``related`` ideas.

    Not a Semrush related-keywords index — title lines that still look like
    something a person might type. Requires whole-token seed coverage (not a
    bare substring hit) so headline junk stays out.
    """
    seed_key = keyword_dedupe_key(seed)
    if not seed_key:
        return []
    out: list[str] = []
    for result in page.results[:_MAX_RELATED_FROM_TITLES]:
        title = collapse_keyword_whitespace(result.title)
        if not title:
            continue
        # Drop site-name suffixes ("Acme CRM — the best…").
        for sep in (" — ", " | ", " - "):
            if sep in title:
                title = collapse_keyword_whitespace(title.split(sep, 1)[0])
                break
        if not looks_like_related_keyword_idea(seed, title):
            continue
        out.append(title)
    return out


class SearxngKeywordSource:
    """Expand a seed via the operator's SearXNG instance."""

    name = "searxng"

    def __init__(self, serp: SearxngSource) -> None:
        self._serp = serp

    @property
    def base_url(self) -> str:
        return self._serp.base_url

    def expand(
        self,
        seed: str,
        *,
        locale: str = "en",
        max_ideas: int = 50,
        max_variants: int = 3,
        exclude_brands: Sequence[str] | None = None,
    ) -> KeywordExpandResult:
        cleaned = collapse_keyword_whitespace(seed)
        if not cleaned:
            return KeywordExpandResult(
                seed="",
                locale=locale,
                ideas=(),
                provider=self.name,
            )

        language = (locale or "en").strip() or "en"
        previous = self._serp.language
        self._serp.language = language
        try:
            try:
                page = self._serp.search(cleaned)
            except SerpUnavailable as exc:
                raise KeywordUnavailable(str(exc)) from exc
        finally:
            self._serp.language = previous

        brand_keys = brand_names_to_exclusion_keys(exclude_brands)
        limit = max(0, max_ideas)
        variant_limit = max(0, max_variants)
        seen: set[str] = set()
        ideas: list[KeywordIdea] = []

        def _append_keyword_idea(phrase: str, source: str) -> None:
            if len(ideas) >= limit:
                return
            text = collapse_keyword_whitespace(phrase)
            key = keyword_dedupe_key(text)
            if not key or key in seen or should_exclude_keyword_candidate(text, brand_keys):
                return
            seen.add(key)
            ideas.append(
                KeywordIdea(
                    phrase=text,
                    source=source,
                    signals=build_estimated_keyword_idea_signals(
                        phrase=text,
                        discovery_source=source,
                        seed_serp_page=page,
                    ),
                )
            )

        _append_keyword_idea(cleaned, "seed")
        for suggestion in page.suggestions:
            _append_keyword_idea(suggestion, "suggestion")
        for answer in page.answers:
            if looks_like_paa_idea(answer):
                _append_keyword_idea(answer, "paa")
        for related in _related_keyword_phrases_from_serp_titles(cleaned, page):
            _append_keyword_idea(related, "related")
        # Local templates last so max_ideas is not spent on filler first.
        for variant in build_seed_query_variants(cleaned, limit=variant_limit):
            _append_keyword_idea(variant, "variant")

        return KeywordExpandResult(
            seed=cleaned,
            locale=locale,
            ideas=tuple(ideas),
            provider=self.name,
        )
