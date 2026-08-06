"""SearXNG keyword expander maps suggestions into KeywordIdea rows."""

from __future__ import annotations

from app.keyword.base import KeywordUnavailable
from app.keyword.searxng_expand import SearxngKeywordSource
from app.serp.base import SerpPage, SerpUnavailable


class _FakeSerp:
    language = "en"
    base_url = "http://searxng:8080"

    def __init__(self, page: SerpPage | None = None, *, error: Exception | None = None):
        self._page = page
        self._error = error
        self.last_query: str | None = None

    def search(self, query: str) -> SerpPage:
        self.last_query = query
        if self._error is not None:
            raise self._error
        assert self._page is not None
        return self._page


def test_expand_maps_suggestions_and_keeps_seed_first():
    page = SerpPage(
        query="money transfer",
        suggestions=("best money transfer", "money transfer uk", "money transfer"),
    )
    source = SearxngKeywordSource(_FakeSerp(page))  # type: ignore[arg-type]
    result = source.expand("money transfer", locale="en-GB", max_ideas=10)
    assert result.provider == "searxng"
    assert result.locale == "en-GB"
    assert [i.phrase for i in result.ideas] == [
        "money transfer",
        "best money transfer",
        "money transfer uk",
    ]
    assert result.ideas[0].source == "seed"
    assert result.ideas[1].source == "suggestion"


def test_expand_respects_max_ideas():
    page = SerpPage(
        query="x",
        suggestions=tuple(f"idea {i}" for i in range(20)),
    )
    source = SearxngKeywordSource(_FakeSerp(page))  # type: ignore[arg-type]
    result = source.expand("x", max_ideas=3)
    assert len(result.ideas) == 3


def test_expand_wraps_serp_unavailable():
    source = SearxngKeywordSource(
        _FakeSerp(error=SerpUnavailable("down"))  # type: ignore[arg-type]
    )
    try:
        source.expand("money transfer")
        raise AssertionError("expected KeywordUnavailable")
    except KeywordUnavailable as exc:
        assert "down" in str(exc)


def test_expand_empty_seed_returns_no_ideas():
    source = SearxngKeywordSource(_FakeSerp(SerpPage(query="")))  # type: ignore[arg-type]
    result = source.expand("   ")
    assert result.ideas == ()
