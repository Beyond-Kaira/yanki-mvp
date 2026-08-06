"""Deterministic, network-free keyword source used whenever ``DRY_RUN`` is on.

Not the product default. Preview and normal local/deployed runs use SearXNG.
This exists so CI and first-run can exercise the registry and (later) API
without a search instance or outbound packets — same role as ``MockSerpSource``.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.keyword.base import KeywordExpandResult, KeywordIdea
from app.keyword.normalize import (
    brand_names_to_exclusion_keys,
    collapse_keyword_whitespace,
    keyword_dedupe_key,
    should_exclude_keyword_candidate,
)
from app.keyword.variants import build_seed_query_variants


class MockKeywordSource:
    name = "mock"

    def expand(
        self,
        seed: str,
        *,
        locale: str = "en",
        max_ideas: int = 50,
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

        brand_keys = brand_names_to_exclusion_keys(exclude_brands)
        limit = max(0, max_ideas)
        seen: set[str] = set()
        ideas: list[KeywordIdea] = []

        def _append_keyword_idea(phrase: str, source: str) -> None:
            if len(ideas) >= limit:
                return
            text = collapse_keyword_whitespace(phrase)
            key = keyword_dedupe_key(text)
            if (
                not key
                or key in seen
                or should_exclude_keyword_candidate(text, brand_keys)
            ):
                return
            seen.add(key)
            ideas.append(KeywordIdea(phrase=text, source=source))

        _append_keyword_idea(cleaned, "seed")
        for variant in build_seed_query_variants(cleaned):
            _append_keyword_idea(variant, "variant")
        # Extra mock-only rows so DRY_RUN tables are obviously synthetic.
        for extra in (
            f"how to {cleaned}",
            f"{cleaned} vs competitors",
        ):
            _append_keyword_idea(extra, "mock")

        return KeywordExpandResult(
            seed=cleaned,
            locale=locale,
            ideas=tuple(ideas),
            provider=self.name,
        )
