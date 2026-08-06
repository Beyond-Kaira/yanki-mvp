"""Deterministic, network-free keyword source used whenever ``DRY_RUN`` is on.

Not the product default. Preview and normal local/deployed runs use SearXNG.
This exists so CI and first-run can exercise the registry and (later) API
without a search instance or outbound packets — same role as ``MockSerpSource``.
"""

from __future__ import annotations

from app.keyword.base import KeywordExpandResult, KeywordIdea


class MockKeywordSource:
    name = "mock"

    def expand(
        self,
        seed: str,
        *,
        locale: str = "en",
        max_ideas: int = 50,
    ) -> KeywordExpandResult:
        cleaned = " ".join((seed or "").split()).strip()
        if not cleaned:
            return KeywordExpandResult(
                seed="",
                locale=locale,
                ideas=(),
                provider=self.name,
            )
        # Stable, obvious fakes so UI/tests can spot mock mode immediately.
        templates = (
            f"{cleaned}",
            f"best {cleaned}",
            f"{cleaned} comparison",
            f"{cleaned} reviews",
            f"{cleaned} alternatives",
            f"how to {cleaned}",
            f"{cleaned} for business",
            f"cheap {cleaned}",
            f"{cleaned} vs competitors",
            f"top {cleaned} companies",
        )
        ideas = tuple(
            KeywordIdea(phrase=phrase, source="mock")
            for phrase in templates[: max(0, max_ideas)]
        )
        return KeywordExpandResult(
            seed=cleaned,
            locale=locale,
            ideas=ideas,
            provider=self.name,
        )
