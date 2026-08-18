"""Pure parser, rule, schema, discovery, URL-boundary, and scoring tests."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import httpx

from app.site_audit.analyzer import analyze_page
from app.site_audit.crawler import (
    UnsafeCrawlTarget,
    _Frontier,
    _HostAllowCache,
    _is_browser_http_url,
    _next_delay_seconds,
    _read_limited_response,
    _read_robots,
    _read_sitemaps,
    _robots_for_url,
    _route_browser_request,
    _scope_key,
    normalize_crawl_url,
)
from app.site_audit.models import CrawlConfig, CrawledPage
from app.site_audit.profiles import get_profile
from app.site_audit.schema_validator import validate_schemas
from app.site_audit.scoring import audit_health_score, page_health_score


def _crawl_config() -> CrawlConfig:
    return CrawlConfig(
        page_limit=10,
        profile=get_profile("site_audit_mobile"),
        js_rendering=True,
        render_wait_ms=0,
        page_timeout_ms=1_000,
        crawl_delay_seconds=0,
        max_robots_bytes=512,
        sitemap_url_limit=100,
        max_sitemap_bytes=1_024,
        max_html_chars=10_000,
        max_queue_urls=100,
    )


def test_analyzer_returns_structured_findings_and_schema_results() -> None:
    page = CrawledPage(
        requested_url="https://example.com/",
        final_url="https://example.com/",
        status_code=200,
        raw_html="""
        <html><head><title>A title that exists</title>
        <script type="application/ld+json">
          {"@context":"https://schema.org","@type":"Organization",
           "name":"Acme","notARealProperty":"x"}
        </script></head><body><img src="hero.png"><a href="/empty"></a></body></html>
        """,
    )

    analyzed = analyze_page(page)

    assert {issue["code"] for issue in analyzed.issues} == {
        "missing_h1",
        "missing_meta_description",
        "missing_html_lang",
        "missing_image_alt",
        "empty_anchor_text",
    }
    assert analyzed.schemas[0]["type"] == "Organization"
    assert analyzed.schemas[0]["syntax_valid"] is True
    assert "notARealProperty" in analyzed.schemas[0]["details"]["invalid_fields"]


def test_schema_validator_reports_invalid_json_and_unknown_type() -> None:
    results = validate_schemas(
        [
            "{broken",
            '{"@context":"https://schema.org","@type":"MadeUpType","name":"x"}',
        ]
    )

    assert results[0]["syntax_valid"] is False
    assert results[0]["type"] == "Parse Error"
    assert results[1]["syntax_valid"] is True
    assert "not a recognized" in results[1]["structure_status"]

    recognized = validate_schemas(
        ['{"@context":"https://schema.org","@type":"Organization","name":"x"}']
    )[0]
    assert "Type and property names are recognized" in recognized["structure_status"]
    assert "Fully valid" not in recognized["structure_status"]


def test_frontier_stays_on_domain_and_port_and_limits_query_variants() -> None:
    frontier = _Frontier("https://www.example.com/", _crawl_config())

    assert frontier.add("https://example.com/about#team") is True
    assert frontier.add("http://example.com/from-http") is True
    assert frontier.add("https://example.com:444/private") is False
    assert frontier.add("https://outside.example.org/") is False
    assert frontier.add("https://example.com/search?q=1&utm_source=x") is True
    assert frontier.add("https://example.com/search?q=2") is True
    assert frontier.add("https://example.com/search?q=3") is True
    assert frontier.add("https://example.com/search?q=4") is False


def test_url_normalization_removes_tracking_and_rejects_binary_files() -> None:
    assert (
        normalize_crawl_url("HTTPS://EXAMPLE.COM:443/a?utm_source=x&b=2&a=1#top")
        == "https://example.com/a?a=1&b=2"
    )
    assert normalize_crawl_url("https://example.com/report.pdf") is None


def test_robots_and_nested_sitemaps_stay_inside_project_scope() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200,
                text="User-agent: *\nDisallow: /private\nSitemap: /sitemap.xml",
            )
        if request.url.path == "/sitemap.xml":
            return httpx.Response(
                200,
                text=(
                    "<sitemapindex>"
                    "<sitemap><loc>/nested.xml</loc></sitemap>"
                    "<sitemap><loc>https://outside.example/sitemap.xml</loc></sitemap>"
                    "</sitemapindex>"
                ),
            )
        if request.url.path == "/nested.xml":
            return httpx.Response(
                200,
                text=(
                    "<urlset><url><loc>/one</loc></url>"
                    "<url><loc>https://example.com/two</loc></url>"
                    "<url><loc>https://outside.example/page</loc></url></urlset>"
                ),
            )
        raise AssertionError(f"unexpected request: {request.url}")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        robots = _read_robots(
            client,
            "https://example.com/",
            "YankiSiteAuditBot",
            512,
        )
        pages = _read_sitemaps(
            client,
            list(robots.sitemaps),
            _crawl_config(),
            _scope_key("https://example.com/"),
        )

    assert robots.status == "ok"
    assert (
        robots.policy.allows(
            "YankiSiteAuditBot",
            "https://example.com/private",
        )
        is False
    )
    assert pages == ["https://example.com/one", "https://example.com/two"]
    assert all("outside.example" not in url for url in requested)


def test_stream_reader_stops_as_soon_as_decoded_byte_limit_is_exceeded() -> None:
    class CountingStream(httpx.SyncByteStream):
        def __init__(self) -> None:
            self.chunks_read = 0
            self.closed = False

        def __iter__(self):
            for chunk in (b"1234", b"56", b"should-not-be-read"):
                self.chunks_read += 1
                yield chunk

        def close(self) -> None:
            self.closed = True

    stream = CountingStream()
    transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=stream))

    with httpx.Client(transport=transport) as client:
        response = _read_limited_response(client, "https://example.com/data", 5)

    assert response.status == "byte_overflow"
    assert stream.chunks_read == 2
    assert stream.closed is True


def test_redirected_origin_loads_and_applies_its_own_robots_policy() -> None:
    requested_origins: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_origins.append(str(request.url.copy_with(path="/", query=None)))
        disallow = "/private" if request.url.host == "www.example.com" else ""
        return httpx.Response(200, text=f"User-agent: *\nDisallow: {disallow}")

    cache = {}
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        seed_policy = _robots_for_url(
            client,
            cache,
            "http://example.com/start",
            "YankiSiteAuditBot",
            512,
        )
        final_policy = _robots_for_url(
            client,
            cache,
            "https://www.example.com/private",
            "YankiSiteAuditBot",
            512,
        )

    assert seed_policy.policy.allows(
        "YankiSiteAuditBot",
        "http://example.com/start",
    )
    assert not final_policy.policy.allows(
        "YankiSiteAuditBot",
        "https://www.example.com/private",
    )
    assert requested_origins == ["http://example.com/", "https://www.example.com/"]


def test_redirect_target_disallowed_by_robots_is_never_fetched(monkeypatch) -> None:
    policy_requests: list[str] = []
    browser_fetches: list[str] = []
    navigation_blocks = []

    def handler(request: httpx.Request) -> httpx.Response:
        policy_requests.append(str(request.url))
        assert request.url.path == "/robots.txt"
        return httpx.Response(200, text="User-agent: *\nDisallow: /private")

    class FakeRoute:
        aborted = False

        def abort(self, error_code: str) -> None:
            assert error_code == "blockedbyclient"
            self.aborted = True

        def continue_(self) -> None:
            browser_fetches.append(request.url)

    request = SimpleNamespace(
        resource_type="document",
        url="https://www.example.com/private",
        frame=SimpleNamespace(parent_frame=None),
        is_navigation_request=lambda: True,
    )
    route = FakeRoute()
    monkeypatch.setattr("app.site_audit.crawler.is_public_url", lambda url: True)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        _route_browser_request(
            route,
            request,
            scope_key=_scope_key("http://example.com/start"),
            policy_client=client,
            robots_cache={},
            robots_user_agent="YankiSiteAuditBot",
            max_robots_bytes=512,
            host_allow_cache=_HostAllowCache(),
            on_navigation_blocked=navigation_blocks.append,
        )

    assert route.aborted is True
    assert browser_fetches == []
    assert policy_requests == ["https://www.example.com/robots.txt"]
    assert navigation_blocks[0].url == "https://www.example.com/private"
    assert navigation_blocks[0].robots.safely_read is True


def test_robots_network_and_overflow_fail_conservatively() -> None:
    def network_failure(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("robots timed out", request=request)

    with httpx.Client(transport=httpx.MockTransport(network_failure)) as client:
        network = _read_robots(
            client,
            "https://example.com/",
            "YankiSiteAuditBot",
            512,
        )

    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"x" * 513)
        )
    ) as client:
        overflow = _read_robots(
            client,
            "https://example.com/",
            "YankiSiteAuditBot",
            512,
        )

    for result, expected_status in (
        (network, "network_error"),
        (overflow, "byte_overflow"),
    ):
        assert result.status == expected_status
        assert result.safely_read is False
        assert result.policy.parser is None
        assert result.policy.allows("YankiSiteAuditBot", "https://example.com/") is False


def test_robots_read_result_distinguishes_missing_unsafe_and_server_errors() -> None:
    def read_with(handler):
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            return _read_robots(
                client,
                "https://example.com/",
                "YankiSiteAuditBot",
                512,
            )

    missing = read_with(lambda request: httpx.Response(404))

    def unsafe(request: httpx.Request) -> httpx.Response:
        raise UnsafeCrawlTarget("redirect resolved to a private address")

    unsafe_redirect = read_with(unsafe)
    server_error = read_with(lambda request: httpx.Response(503))

    assert missing.status == "not_found"
    assert missing.safely_read is True
    assert missing.policy.allows("YankiSiteAuditBot", "https://example.com/") is True
    assert unsafe_redirect.status == "unsafe_redirect"
    assert unsafe_redirect.safely_read is False
    assert unsafe_redirect.error == "redirect resolved to a private address"
    assert server_error.status == "http_error"
    assert server_error.status_code == 503
    assert server_error.safely_read is False


def test_browser_route_scheme_allowlist_is_fail_closed() -> None:
    assert _is_browser_http_url("https://example.com") is True
    assert _is_browser_http_url("http://example.com") is True
    for url in ("file:///etc/passwd", "data:text/plain,test", "ftp://example.com"):
        assert _is_browser_http_url(url) is False


def test_public_host_verdicts_are_memoized_for_the_rest_of_the_crawl(monkeypatch) -> None:
    """The guard blocks Playwright's dispatcher, so repeat lookups are latency.

    Every subresource used to pay a fresh ``getaddrinfo`` for an answer the
    crawl already had, out of the same 30s budget the navigation was being
    timed against.
    """

    resolutions: list[str] = []

    def counting_guard(url: str) -> bool:
        resolutions.append(url)
        return "allowed" in url

    monkeypatch.setattr("app.site_audit.crawler.is_public_url", counting_guard)
    cache = _HostAllowCache()

    for path in ("/a.js", "/b.css", "/c.json"):
        assert cache.is_public(f"https://allowed.example.com{path}") is True
    assert len(resolutions) == 1

    # Denials are cached too, or one dead third-party host costs a full
    # resolver timeout on every subresource that references it.
    for path in ("/x.js", "/y.css"):
        assert cache.is_public(f"https://blocked.example.com{path}") is False
    assert len(resolutions) == 2

    # Keyed by host alone: the port and path do not change who we are talking
    # to. Reached only on a cache hit — a miss would re-run the guard, which
    # does not recognize this URL and would answer False.
    assert cache.is_public("https://ALLOWED.example.com:8443/z.js") is True
    assert len(resolutions) == 2

    # An expired verdict is re-resolved rather than served stale.
    cache.denied_until["blocked.example.com"] = 0.0
    assert cache.is_public("https://blocked.example.com/x.js") is False
    assert len(resolutions) == 3


def test_failure_backoff_grows_from_the_politeness_floor_and_stops_at_the_cap() -> None:
    # A healthy crawl is unaffected: no failures, no backoff.
    assert _next_delay_seconds(0.25, 0, 10.0) == 0.25

    # Consecutive failures double the wait, then hold at the cap.
    assert _next_delay_seconds(0.25, 1, 10.0) == 1.0
    assert _next_delay_seconds(0.25, 2, 10.0) == 2.0
    assert _next_delay_seconds(0.25, 4, 10.0) == 8.0
    assert _next_delay_seconds(0.25, 5, 10.0) == 10.0
    assert _next_delay_seconds(0.25, 40, 10.0) == 10.0

    # The floor wins whenever it is the larger of the two. A site declaring
    # Crawl-delay: 30 is still waited on for 30s while we are failing, and a cap
    # set below that floor never talks us into being ruder than robots.txt asks.
    assert _next_delay_seconds(30.0, 3, 10.0) == 30.0

    # An operator who disabled the politeness delay still gets backed off, since
    # 0 means "do not be slow against a healthy site", not "hammer a failing one".
    assert _next_delay_seconds(0, 1, 10.0) == 1.0
    assert _next_delay_seconds(0, 0, 10.0) == 0

    # A zero cap disables backoff without disabling the floor.
    assert _next_delay_seconds(0.25, 3, 0) == 0.25


def test_health_score_excludes_robots_and_uses_visible_penalties() -> None:
    warning = [{"code": "missing_h1", "severity": "warning"}]
    robots = [{"code": "blocked_by_robots", "severity": "notice"}]

    assert page_health_score(200, warning) == 95
    assert page_health_score(500, []) == 0
    assert page_health_score(0, robots) is None
    assert audit_health_score([95, 0, None]) == 48
    assert audit_health_score([None]) is None


def test_schema_source_metadata_matches_bundled_ontology() -> None:
    data_dir = Path(__file__).parents[1] / "app" / "site_audit" / "data"
    ontology = data_dir / "schema_master.json"
    metadata = json.loads((data_dir / "schema_master.source.json").read_text("utf-8"))

    # Text mode normalizes checkout-specific CRLF/LF line endings.
    ontology_bytes = ontology.read_text(encoding="utf-8").encode("utf-8")

    assert hashlib.sha256(ontology_bytes).hexdigest().upper() == metadata["sha256"]
    assert metadata["retrieval_date"] is None
    assert metadata["license"] == "CC BY-SA 3.0"
    assert metadata["verified_schema_version"] is None
