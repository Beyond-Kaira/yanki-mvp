"""SearXNG adapter tests.

Uses respx to intercept the httpx call so nothing ever leaves the process. The
payloads below are trimmed from a **real** 2026.8 instance's response rather than
invented, because the whole job of this adapter is to survive the shape a real
instance actually sends — including the two things the docs do not mention:
``number_of_results`` comes back null, and ``unresponsive_engines`` is a list of
``[name, reason]`` pairs.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.serp.base import SerpUnavailable
from app.serp.searxng import SearxngSource

BASE_URL = "http://searxng.internal:8080"
SEARCH_URL = f"{BASE_URL}/search"

# Trimmed from a live instance. Field-for-field what SearXNG sends.
LIVE_PAYLOAD = {
    "query": "best crm software",
    "results": [
        {
            "url": "https://www.acmecrm.example/",
            "title": "Acme CRM — the best CRM software",
            "content": "Acme CRM is a customer relationship platform.",
            "engine": "google",
            "parsed_url": ["https", "www.acmecrm.example", "/", "", "", ""],
            "engines": ["google"],
            "positions": [1],
            "score": 1.0,
            "category": "general",
            "template": "default.html",
            "publishedDate": None,
        },
        {
            "url": "https://reviews.example/top-crm",
            "title": "The 8 best CRM systems compared",
            "content": "We compare Acme CRM, Globex and others.",
            "engines": ["duckduckgo", "brave"],
            "positions": [2, 3],
            "score": 0.5,
            "category": "general",
        },
    ],
    "answers": [],
    "corrections": [],
    "infoboxes": [],
    "suggestions": [],
    "unresponsive_engines": [],
}


@respx.mock
def test_parses_a_live_shaped_payload_into_ranked_results():
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json=LIVE_PAYLOAD))

    page = SearxngSource(BASE_URL).search("best crm software")

    assert page.query == "best crm software"
    assert [r.rank for r in page.results] == [1, 2]
    assert page.results[0].url == "https://www.acmecrm.example/"
    assert page.results[0].title == "Acme CRM — the best CRM software"
    assert page.results[0].engine == "google"
    # No ``engine`` key on the second result: fall back to the first of ``engines``.
    assert page.results[1].engine == "duckduckgo"
    assert page.unresponsive_engines == ()
    assert page.measurable is True


@respx.mock
def test_sends_the_documented_query_parameters():
    route = respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json=LIVE_PAYLOAD))

    SearxngSource(BASE_URL, language="tr", categories="general", safesearch=1).search("robots")

    params = route.calls.last.request.url.params
    assert params["q"] == "robots"
    assert params["format"] == "json"
    assert params["language"] == "tr"
    assert params["categories"] == "general"
    assert params["safesearch"] == "1"
    assert params["pageno"] == "1"
    # No allowlist configured -> the parameter is omitted entirely rather than
    # sent empty, which SearXNG would read as "no engines at all".
    assert "engines" not in params


@respx.mock
def test_engine_allowlist_is_passed_through_when_configured():
    route = respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json=LIVE_PAYLOAD))

    SearxngSource(BASE_URL, engines="google,duckduckgo").search("robots")

    assert route.calls.last.request.url.params["engines"] == "google,duckduckgo"


@respx.mock
def test_a_blocked_panel_is_reported_rather_than_read_as_an_empty_serp():
    """The failure mode this whole design exists for.

    A live instance answers 200 with no results when every upstream engine
    rate-limited it. That page must not be scoreable.
    """
    respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "query": "best crm software",
                "results": [],
                "unresponsive_engines": [
                    ["brave", "Suspended: too many requests"],
                    ["duckduckgo", "CAPTCHA"],
                ],
            },
        )
    )

    page = SearxngSource(BASE_URL).search("best crm software")

    assert page.results == ()
    assert page.unresponsive_engines == ("brave", "duckduckgo")
    assert page.measurable is False


@respx.mock
def test_an_empty_page_from_a_healthy_instance_is_a_real_answer():
    respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(200, json={"query": "x", "results": []})
    )

    page = SearxngSource(BASE_URL).search("x")

    assert page.results == ()
    assert page.measurable is True


@respx.mock
def test_partial_results_stay_measurable_even_with_engines_down():
    respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "query": "x",
                "results": [{"url": "https://a.example/", "title": "A"}],
                "unresponsive_engines": [["brave", "CAPTCHA"]],
            },
        )
    )

    assert SearxngSource(BASE_URL).search("x").measurable is True


@respx.mock
@pytest.mark.parametrize(
    "raw",
    [
        ["brave", "duckduckgo"],
        [["brave", "CAPTCHA"], ["duckduckgo", "CAPTCHA"]],
        [{"name": "brave"}, {"engine": "duckduckgo"}],
    ],
    ids=["strings", "pairs", "objects"],
)
def test_unresponsive_engines_is_read_in_every_shape_the_field_has_carried(raw):
    respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(
            200, json={"query": "x", "results": [], "unresponsive_engines": raw}
        )
    )

    page = SearxngSource(BASE_URL).search("x")

    assert page.unresponsive_engines == ("brave", "duckduckgo")


@respx.mock
def test_results_are_capped_and_reranked_contiguously():
    payload = {
        "query": "x",
        "results": [{"url": f"https://s{i}.example/", "title": f"S{i}"} for i in range(50)],
    }
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json=payload))

    page = SearxngSource(BASE_URL, max_results=5).search("x")

    assert [r.rank for r in page.results] == [1, 2, 3, 4, 5]


@respx.mock
def test_junk_entries_are_skipped_without_leaving_a_rank_gap():
    """A urlless or non-dict entry must not consume a rank.

    Ranks are what the product reports ("you appear at position 3"), so a
    skipped entry that still advanced the counter would misreport every result
    below it.
    """
    payload = {
        "query": "x",
        "results": [
            "not-a-dict",
            {"title": "no url here"},
            {"url": "https://real.example/", "title": "Real"},
        ],
    }
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json=payload))

    page = SearxngSource(BASE_URL).search("x")

    assert len(page.results) == 1
    assert page.results[0].rank == 1


@respx.mock
def test_non_200_is_unavailable_not_an_empty_page():
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(403))

    with pytest.raises(SerpUnavailable):
        SearxngSource(BASE_URL).search("x")


@respx.mock
def test_html_instead_of_json_is_unavailable():
    """What an instance serves when its operator forgot ``formats: [html, json]``."""
    respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(200, text="<!doctype html><html>results</html>")
    )

    with pytest.raises(SerpUnavailable):
        SearxngSource(BASE_URL).search("x")


@respx.mock
def test_a_transport_error_is_unavailable():
    respx.get(SEARCH_URL).mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(SerpUnavailable):
        SearxngSource(BASE_URL).search("x")


def test_an_unconfigured_base_url_is_unavailable_without_a_request():
    with pytest.raises(SerpUnavailable):
        SearxngSource("").search("x")


@respx.mock
def test_a_trailing_slash_on_the_base_url_does_not_double_up():
    route = respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json=LIVE_PAYLOAD))

    SearxngSource(f"{BASE_URL}/").search("x")

    assert route.called
