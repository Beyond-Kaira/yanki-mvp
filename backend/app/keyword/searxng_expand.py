"""SearXNG-backed keyword expansion (open-source preview path).

Phase 1 seam: wrap the existing :class:`~app.serp.searxng.SearxngSource` and
map its ``suggestions`` into :class:`~app.keyword.base.KeywordIdea` rows.
Richer expansion (related, PAA, query variants, normalize) lands in the next
implementation step — same class, fuller ``expand``.
"""

from __future__ import annotations

from app.keyword.base import KeywordExpandResult, KeywordIdea, KeywordUnavailable
from app.serp.base import SerpUnavailable
from app.serp.searxng import SearxngSource


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
    ) -> KeywordExpandResult:
        cleaned = " ".join((seed or "").split()).strip()
        if not cleaned:
            return KeywordExpandResult(
                seed="",
                locale=locale,
                ideas=(),
                provider=self.name,
            )

        # Locale for preview maps onto SearXNG's language pin for this call.
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

        limit = max(0, max_ideas)
        seen: set[str] = set()
        ideas: list[KeywordIdea] = []

        def _add(phrase: str, source: str) -> None:
            key = " ".join(phrase.lower().split())
            if not key or key in seen or len(ideas) >= limit:
                return
            seen.add(key)
            ideas.append(KeywordIdea(phrase=" ".join(phrase.split()), source=source))

        # Always include the seed itself as the first row (Overview/Magic habit).
        _add(cleaned, "seed")
        for suggestion in page.suggestions:
            _add(suggestion, "suggestion")

        return KeywordExpandResult(
            seed=cleaned,
            locale=locale,
            ideas=tuple(ideas),
            provider=self.name,
        )
