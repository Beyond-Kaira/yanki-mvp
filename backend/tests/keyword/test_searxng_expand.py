"""SearXNG keyword expander: variants + suggestions + PAA + related titles."""

from __future__ import annotations

from app.keyword.base import KeywordUnavailable
from app.keyword.searxng_expand import SearxngKeywordSource
from app.serp.base import SerpPage, SerpResult, SerpUnavailable


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


def test_expand_includes_seed_variants_suggestions_paa_and_related():
    page = SerpPage(
        query="money transfer",
        results=(
            SerpResult(
                rank=1,
                url="https://example.com/a",
                title="Best money transfer apps — Guide",
            ),
            SerpResult(
                rank=2,
                url="https://example.com/b",
                title="Unrelated banking news",
            ),
        ),
        suggestions=("money transfer uk", "international money transfer"),
        answers=("is money transfer safe", "A long prose answer that ends."),
    )
    source = SearxngKeywordSource(_FakeSerp(page))  # type: ignore[arg-type]
    result = source.expand("money transfer", locale="en-GB", max_ideas=50)

    assert result.provider == "searxng"
    assert result.locale == "en-GB"
    by_source: dict[str, list[str]] = {}
    for idea in result.ideas:
        by_source.setdefault(idea.source, []).append(idea.phrase)

    assert by_source["seed"] == ["money transfer"]
    assert "best money transfer" in by_source["variant"]
    assert "money transfer uk" in by_source["suggestion"]
    assert "is money transfer safe" in by_source["paa"]
    assert "Best money transfer apps" in by_source["related"]
    assert "A long prose answer that ends." not in [
        p for rows in by_source.values() for p in rows
    ]
    suggestion = next(i for i in result.ideas if i.phrase == "money transfer uk")
    assert suggestion.signals["volume_estimated"] is True
    assert suggestion.signals["intent"]
    assert suggestion.signals["difficulty_basis"] == "seed_serp"


def test_expand_drops_excluded_brands_and_respects_max_ideas():
    page = SerpPage(
        query="transfer",
        suggestions=("Wise transfer", "transfer comparison", "transfer reviews"),
    )
    source = SearxngKeywordSource(_FakeSerp(page))  # type: ignore[arg-type]
    result = source.expand(
        "transfer",
        max_ideas=4,
        exclude_brands=["Wise"],
    )
    assert len(result.ideas) == 4
    assert all("wise" not in idea.phrase.lower() for idea in result.ideas)


def test_expand_dedupes_case_and_whitespace():
    page = SerpPage(
        query="crm",
        suggestions=("Best CRM", "best   crm", "BEST CRM"),
    )
    source = SearxngKeywordSource(_FakeSerp(page))  # type: ignore[arg-type]
    result = source.expand("crm", max_ideas=20)
    keys = [idea.phrase.lower() for idea in result.ideas]
    assert len(keys) == len(set(keys))


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
