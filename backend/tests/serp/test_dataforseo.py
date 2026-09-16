"""DataForSEO SERP adapter tests — fixture-shaped payloads, no live API calls."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from app.serp.base import SerpUnavailable
from app.serp.dataforseo import (
    API_URL,
    DataForSeoSource,
    location_code_for_language,
    page_from_api_payload,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "dataforseo_organic.json"


@pytest.fixture
def live_payload() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


def test_location_code_maps_common_languages():
    assert location_code_for_language("en") == 2840
    assert location_code_for_language("tr") == 2792
    assert location_code_for_language("en-gb") == 2826


def test_parses_organic_related_and_paa_from_fixture(live_payload):
    page = page_from_api_payload(live_payload, query="best crm software", max_results=20)

    assert page.query == "best crm software"
    assert [r.rank for r in page.results] == [1, 2]
    assert page.results[0].url == "https://www.acmecrm.example/"
    assert page.results[0].engine == "google"
    assert page.suggestions == ("crm for small business", "free crm software")
    assert page.answers == ("What is the best CRM for startups?",)
    assert page.unresponsive_engines == ()
    assert page.measurable is True


def test_empty_organic_is_measurable_without_unresponsive_engines(live_payload):
    live_payload["tasks"][0]["result"][0]["items"] = [
        {"type": "related_searches", "items": ["crm tools"]}
    ]
    page = page_from_api_payload(live_payload, query="best crm software", max_results=20)

    assert page.results == ()
    assert page.measurable is True


def test_api_level_error_raises_unavailable():
    with pytest.raises(SerpUnavailable, match="40202"):
        page_from_api_payload(
            {"status_code": 40202, "status_message": "Payment Required."},
            query="x",
            max_results=10,
        )


def test_task_level_error_raises_unavailable(live_payload):
    live_payload["tasks"][0]["status_code"] = 40000
    live_payload["tasks"][0]["status_message"] = "Task failed."

    with pytest.raises(SerpUnavailable, match="Task failed"):
        page_from_api_payload(live_payload, query="best crm software", max_results=20)


@respx.mock
def test_live_search_posts_task_and_parses_response(live_payload):
    route = respx.post(API_URL).mock(return_value=httpx.Response(200, json=live_payload))

    page = DataForSeoSource("login", "secret", language="en", location_code=2840).search(
        "best crm software"
    )

    assert page.results[0].title.startswith("Acme CRM")
    request = route.calls.last.request
    assert request.headers["Authorization"].startswith("Basic ")
    body = json.loads(request.content.decode())
    assert body[0]["keyword"] == "best crm software"
    assert body[0]["language_code"] == "en"
    assert body[0]["location_code"] == 2840
    assert body[0]["device"] == "desktop"


@respx.mock
def test_http_401_is_a_clear_credential_error(live_payload):
    respx.post(API_URL).mock(return_value=httpx.Response(401, json=live_payload))

    with pytest.raises(SerpUnavailable, match="credentials"):
        DataForSeoSource("bad", "bad").search("robots")


def test_missing_credentials_raise_before_http():
    with pytest.raises(SerpUnavailable, match="credentials"):
        DataForSeoSource("", "").search("robots")
