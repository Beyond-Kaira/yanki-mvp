"""Bounded same-site browser crawler with robots, sitemap, and SSRF protection."""

from __future__ import annotations

import ipaddress
import logging
import time
import urllib.robotparser
import xml.etree.ElementTree as ET
from collections import defaultdict, deque
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx
from playwright.sync_api import Request, Route, sync_playwright

from app.net_guard import is_public_url
from app.site_audit.models import CrawlConfig, CrawledPage
from app.site_audit.parser import extract_links

logger = logging.getLogger("yanki.site_audit.crawler")

PageCallback = Callable[[CrawledPage, int], None]
DiscoveryCallback = Callable[[int], None]
HeartbeatCallback = Callable[[], None]

# Where the consecutive-failure backoff starts doubling from. Deliberately not
# derived from ``crawl_delay_seconds``: an operator who sets that to 0 is saying
# "do not be slow against a healthy site", not "hammer one that is failing".
_FAILURE_BACKOFF_SEED_SECONDS = 1.0

_HTML_CONTENT_TYPES = frozenset({"text/html", "application/xhtml+xml"})
_BLOCKED_RESOURCE_TYPES = frozenset({"image", "media", "font"})
_TRACKING_QUERY_KEYS = frozenset(
    {
        "fbclid",
        "gclid",
        "msclkid",
        "mc_cid",
        "mc_eid",
    }
)
_EXCLUDED_EXTENSIONS = (
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".csv",
    ".zip",
    ".rar",
    ".7z",
    ".gz",
    ".tar",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".mp4",
    ".mp3",
    ".avi",
    ".mov",
    ".wav",
    ".webm",
    ".css",
    ".js",
    ".json",
    ".xml",
    ".rss",
)


class UnsafeCrawlTarget(RuntimeError):
    pass


def _normalize_http_url(value: str, *, exclude_binary: bool) -> str | None:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None

    try:
        host = parsed.hostname.rstrip(".").lower().encode("idna").decode("ascii")
    except UnicodeError:
        return None

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        formatted_host = host
    else:
        formatted_host = f"[{host}]" if ip.version == 6 else host

    scheme = parsed.scheme.lower()
    default_port = 443 if scheme == "https" else 80
    port_suffix = f":{port}" if port is not None and port != default_port else ""
    path = parsed.path or "/"
    if exclude_binary and path.lower().endswith(_EXCLUDED_EXTENSIONS):
        return None

    query_pairs = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_QUERY_KEYS and not key.lower().startswith("utm_")
    ]
    query = urlencode(sorted(query_pairs))
    return urlunsplit((scheme, f"{formatted_host}{port_suffix}", path, query, ""))


def normalize_crawl_url(value: str) -> str | None:
    return _normalize_http_url(value, exclude_binary=True)


def _scope_key(url: str) -> tuple[str, int | None]:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    host = host[4:] if host.startswith("www.") else host
    default_port = 443 if parsed.scheme.lower() == "https" else 80
    custom_port = parsed.port if parsed.port is not None and parsed.port != default_port else None
    return host, custom_port


def _same_scope(url: str, scope_key: tuple[str, int | None]) -> bool:
    return _scope_key(url) == scope_key


class _Frontier:
    def __init__(self, seed_url: str, config: CrawlConfig):
        self.config = config
        self.scope_key = _scope_key(seed_url)
        self.queue: deque[str] = deque()
        self.visited: set[str] = set()
        self.query_variants: dict[tuple[str, str], int] = defaultdict(int)
        self.add(seed_url)

    def add(self, value: str) -> bool:
        normalized = normalize_crawl_url(value)
        if normalized is None or not _same_scope(normalized, self.scope_key):
            return False
        if normalized in self.visited or len(self.visited) >= self.config.max_queue_urls:
            return False

        parsed = urlsplit(normalized)
        variant_key = ((parsed.hostname or "").lower(), parsed.path or "/")
        if parsed.query:
            if self.query_variants[variant_key] >= self.config.max_query_variants_per_path:
                return False
            self.query_variants[variant_key] += 1

        self.visited.add(normalized)
        self.queue.append(normalized)
        return True


@dataclass
class _RobotsPolicy:
    parser: urllib.robotparser.RobotFileParser | None
    crawl_delay_seconds: float
    allow_without_parser: bool

    def allows(self, user_agent: str, url: str) -> bool:
        if self.parser is None:
            return self.allow_without_parser
        return self.parser.can_fetch(user_agent, url)


@dataclass(frozen=True)
class _LimitedReadResult:
    status: Literal[
        "ok",
        "http_status",
        "network_error",
        "unsafe_redirect",
        "byte_overflow",
    ]
    status_code: int | None = None
    content: bytes = b""
    error: str | None = None


@dataclass(frozen=True)
class _RobotsReadResult:
    status: Literal[
        "ok",
        "not_found",
        "network_error",
        "unsafe_redirect",
        "byte_overflow",
        "http_error",
    ]
    policy: _RobotsPolicy
    sitemaps: tuple[str, ...] = ()
    status_code: int | None = None
    error: str | None = None

    @property
    def safely_read(self) -> bool:
        return self.status in {"ok", "not_found"}


def _guard_http_request(request: httpx.Request) -> None:
    if not is_public_url(str(request.url)):
        raise UnsafeCrawlTarget(f"blocked non-public URL: {request.url}")


def _read_limited_response(
    client: httpx.Client,
    url: str,
    max_bytes: int,
    on_progress: HeartbeatCallback | None = None,
) -> _LimitedReadResult:
    """Read at most ``max_bytes`` decoded bytes, closing the stream on overflow."""

    try:
        if on_progress is not None:
            on_progress()
        with client.stream("GET", url) as response:
            if response.status_code != 200:
                return _LimitedReadResult(
                    status="http_status",
                    status_code=response.status_code,
                )

            content_length = response.headers.get("content-length")
            if content_length is not None:
                try:
                    if int(content_length) > max_bytes:
                        return _LimitedReadResult(
                            status="byte_overflow",
                            status_code=response.status_code,
                            error="content-length exceeds configured byte limit",
                        )
                except ValueError:
                    pass

            content = bytearray()
            for chunk in response.iter_bytes():
                if on_progress is not None:
                    on_progress()
                if len(content) + len(chunk) > max_bytes:
                    return _LimitedReadResult(
                        status="byte_overflow",
                        status_code=response.status_code,
                        error="decoded response exceeds configured byte limit",
                    )
                content.extend(chunk)
            return _LimitedReadResult(
                status="ok",
                status_code=response.status_code,
                content=bytes(content),
            )
    except UnsafeCrawlTarget as exc:
        return _LimitedReadResult(status="unsafe_redirect", error=str(exc)[:500])
    except httpx.HTTPError as exc:
        return _LimitedReadResult(status="network_error", error=str(exc)[:500])


def _read_robots(
    client: httpx.Client,
    seed_url: str,
    robots_user_agent: str,
    max_bytes: int,
    on_progress: HeartbeatCallback | None = None,
) -> _RobotsReadResult:
    parsed_seed = urlsplit(seed_url)
    robots_url = urlunsplit((parsed_seed.scheme, parsed_seed.netloc, "/robots.txt", "", ""))
    response = _read_limited_response(client, robots_url, max_bytes, on_progress)
    if response.status == "http_status":
        if response.status_code in {404, 410}:
            return _RobotsReadResult(
                status="not_found",
                status_code=response.status_code,
                policy=_RobotsPolicy(None, 0, allow_without_parser=True),
            )
        return _RobotsReadResult(
            status="http_error",
            status_code=response.status_code,
            error=f"robots.txt returned HTTP {response.status_code}",
            policy=_RobotsPolicy(None, 0, allow_without_parser=False),
        )
    if response.status != "ok":
        return _RobotsReadResult(
            status=response.status,
            status_code=response.status_code,
            error=response.error,
            policy=_RobotsPolicy(None, 0, allow_without_parser=False),
        )

    lines = response.content.decode("utf-8-sig", errors="replace").splitlines()
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(lines)
    crawl_delay = parser.crawl_delay(robots_user_agent) or 0
    sitemaps = [
        urljoin(robots_url, line.split(":", 1)[1].strip())
        for line in lines
        if line.lower().startswith("sitemap:") and line.split(":", 1)[1].strip()
    ]
    return _RobotsReadResult(
        status="ok",
        policy=_RobotsPolicy(parser, float(crawl_delay), allow_without_parser=False),
        sitemaps=tuple(sitemaps),
        status_code=response.status_code,
    )


def _origin_url(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), "/", "", ""))


def _robots_for_url(
    client: httpx.Client,
    cache: dict[str, _RobotsReadResult],
    url: str,
    robots_user_agent: str,
    max_bytes: int,
    on_progress: HeartbeatCallback | None = None,
) -> _RobotsReadResult:
    origin = _origin_url(url)
    policy = cache.get(origin)
    if policy is None:
        policy = _read_robots(
            client,
            origin,
            robots_user_agent,
            max_bytes,
            on_progress,
        )
        cache[origin] = policy
    return policy


def _local_xml_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _read_sitemaps(
    client: httpx.Client,
    sitemap_urls: list[str],
    config: CrawlConfig,
    scope_key: tuple[str, int | None],
    on_progress: HeartbeatCallback | None = None,
) -> list[str]:
    queue = deque(sitemap_urls)
    seen_sitemaps: set[str] = set()
    page_urls: list[str] = []
    seen_pages: set[str] = set()

    while (
        queue
        and len(page_urls) < config.sitemap_url_limit
        and len(seen_sitemaps) < config.sitemap_url_limit
    ):
        sitemap_url = queue.popleft()
        normalized_sitemap = _normalize_http_url(sitemap_url, exclude_binary=False)
        if (
            normalized_sitemap is None
            or not _same_scope(normalized_sitemap, scope_key)
            or normalized_sitemap in seen_sitemaps
        ):
            continue
        sitemap_url = normalized_sitemap
        seen_sitemaps.add(sitemap_url)

        response = _read_limited_response(
            client,
            sitemap_url,
            config.max_sitemap_bytes,
            on_progress,
        )
        if response.status != "ok":
            continue

        try:
            root = ET.fromstring(response.content)
        except ET.ParseError:
            continue

        root_name = _local_xml_name(root.tag)
        locations = [
            element.text.strip()
            for element in root.iter()
            if _local_xml_name(element.tag) == "loc" and element.text
        ]
        if root_name == "sitemapindex":
            queue.extend(
                urljoin(sitemap_url, location)
                for location in locations
                if location not in seen_sitemaps
            )
        elif root_name == "urlset":
            for location in locations:
                page_url = normalize_crawl_url(urljoin(sitemap_url, location))
                if (
                    page_url is None
                    or not _same_scope(page_url, scope_key)
                    or page_url in seen_pages
                ):
                    continue
                seen_pages.add(page_url)
                page_urls.append(page_url)
                if len(page_urls) >= config.sitemap_url_limit:
                    break

    return page_urls


def _is_browser_http_url(url: str) -> bool:
    return urlsplit(url).scheme.lower() in {"http", "https"}


@dataclass(frozen=True)
class _NavigationBlock:
    url: str
    robots: _RobotsReadResult


# How long one crawl reuses a host's public/private verdict. Allows are held
# long enough to cover a page and everything it pulls; denials only briefly —
# see the class docstring for why the two are not symmetrical.
_HOST_ALLOW_TTL_SECONDS = 300.0
_HOST_DENY_TTL_SECONDS = 30.0
_HOST_CACHE_MAX_ENTRIES = 512


@dataclass
class _HostAllowCache:
    """Per-crawl memo for the public-host guard, keyed by hostname.

    ``is_public_host`` resolves through ``socket.getaddrinfo``, which **blocks**.
    The route handler runs on Playwright's dispatcher, so every uncached lookup
    stalls all browser protocol traffic — including the navigation the crawler
    is currently timing out. One page pulls dozens of subresources off a handful
    of hosts, and without this the guard paid that stall once per *request* for
    an answer it already had. The cost is invisible against a warm local
    resolver and decisive on a contended box, which is how a crawl that is
    healthy on a laptop times out in production.

    Allows and denials are cached differently, on purpose:

    * An allow is cheap to trust. It is the same answer the uncached check
      produced moments earlier, and this guard was never DNS-rebinding
      protection to begin with — Python and Chromium resolve independently, so
      a host that changes answers mid-crawl already defeated it (see
      ``docs/site-audit-integration.md``).
    * A denial is held briefly, because ``is_public_host`` returns False both
      for a genuinely private address *and* for a resolver that merely timed
      out. Holding the second for long would turn one DNS blip into a page that
      cannot load; not holding it at all makes a dead third-party host cost a
      full resolver timeout on every subresource that references it.

    A miss is always safe: correctness never depends on a hit, which is why the
    bound below simply drops the memo instead of evicting carefully.
    """

    allowed_until: dict[str, float] = field(default_factory=dict)
    denied_until: dict[str, float] = field(default_factory=dict)

    def is_public(self, url: str) -> bool:
        host = (urlsplit(url).hostname or "").lower()
        if not host:
            return is_public_url(url)

        now = time.monotonic()
        if self.allowed_until.get(host, 0.0) > now:
            return True
        if self.denied_until.get(host, 0.0) > now:
            return False

        allowed = is_public_url(url)
        cache = self.allowed_until if allowed else self.denied_until
        if len(cache) >= _HOST_CACHE_MAX_ENTRIES:
            cache.clear()
        cache[host] = now + (_HOST_ALLOW_TTL_SECONDS if allowed else _HOST_DENY_TTL_SECONDS)
        return allowed


def _route_browser_request(
    route: Route,
    request: Request,
    *,
    scope_key: tuple[str, int | None],
    policy_client: httpx.Client,
    robots_cache: dict[str, _RobotsReadResult],
    robots_user_agent: str,
    max_robots_bytes: int,
    host_allow_cache: _HostAllowCache,
    on_navigation_blocked: Callable[[_NavigationBlock], None],
) -> None:
    if request.resource_type in _BLOCKED_RESOURCE_TYPES:
        route.abort("blockedbyclient")
        return
    if not _is_browser_http_url(request.url):
        route.abort("blockedbyclient")
        return

    is_main_navigation = request.is_navigation_request() and (request.frame.parent_frame is None)
    if is_main_navigation and not _same_scope(request.url, scope_key):
        route.abort("blockedbyclient")
        return

    # Application-level defence in depth. Resolution and connection are still
    # separate operations; production egress isolation remains unresolved.
    if not host_allow_cache.is_public(request.url):
        route.abort("blockedbyclient")
        return

    if is_main_navigation:
        normalized_url = normalize_crawl_url(request.url)
        if normalized_url is None:
            route.abort("blockedbyclient")
            return
        robots = _robots_for_url(
            policy_client,
            robots_cache,
            normalized_url,
            robots_user_agent,
            max_robots_bytes,
        )
        if not robots.safely_read or not robots.policy.allows(
            robots_user_agent,
            normalized_url,
        ):
            on_navigation_blocked(_NavigationBlock(normalized_url, robots))
            route.abort("blockedbyclient")
            return

    route.continue_()


def _robots_failure_message(result: _RobotsReadResult) -> str:
    detail = result.error or (
        f"HTTP {result.status_code}" if result.status_code is not None else "unknown error"
    )
    return f"robots.txt could not be read safely ({result.status}): {detail}"


def _next_delay_seconds(
    base_delay_seconds: float,
    consecutive_failures: int,
    backoff_max_seconds: float,
) -> float:
    """How long to wait before the next navigation.

    Never below ``base_delay_seconds``: that is the politeness floor, raised to
    the target's own robots.txt ``Crawl-delay`` where it declares one, and a run
    of failures is not permission to ignore it. Above that floor the wait
    doubles per consecutive failure up to ``backoff_max_seconds``, because
    re-asking at full speed is the worst available answer to "the target is not
    responding" — it grows the very load that produced the timeouts.
    """

    if consecutive_failures <= 0:
        return base_delay_seconds
    backoff = min(
        _FAILURE_BACKOFF_SEED_SECONDS * 2 ** (consecutive_failures - 1),
        backoff_max_seconds,
    )
    return max(base_delay_seconds, backoff)


def _is_html_response(headers: dict[str, str]) -> bool:
    content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    return not content_type or content_type in _HTML_CONTENT_TYPES


def crawl_site(
    seed_url: str,
    config: CrawlConfig,
    *,
    on_page: PageCallback,
    on_discovery: DiscoveryCallback | None = None,
    on_heartbeat: HeartbeatCallback | None = None,
) -> int:
    normalized_seed = normalize_crawl_url(seed_url)
    if normalized_seed is None:
        raise ValueError("Site Audit seed must be a valid HTTP or HTTPS URL")
    if not is_public_url(normalized_seed):
        raise UnsafeCrawlTarget("Site Audit seed host is not public")

    frontier = _Frontier(normalized_seed, config)
    headers = {"User-Agent": config.profile.browser_user_agent}
    with httpx.Client(
        headers=headers,
        timeout=15,
        follow_redirects=True,
        event_hooks={"request": [_guard_http_request]},
    ) as client:
        robots = _read_robots(
            client,
            normalized_seed,
            config.profile.robots_user_agent,
            config.max_robots_bytes,
            on_heartbeat,
        )
        sitemap_urls = list(robots.sitemaps)
        if robots.safely_read and not sitemap_urls:
            sitemap_urls = [urljoin(normalized_seed, "/sitemap.xml")]
        for sitemap_page in _read_sitemaps(
            client,
            sitemap_urls,
            config,
            frontier.scope_key,
            on_heartbeat,
        ):
            frontier.add(sitemap_page)

    if on_discovery is not None:
        on_discovery(len(frontier.visited))

    robots_cache = {_origin_url(normalized_seed): robots}
    host_allow_cache = _HostAllowCache()
    processed = 0
    with ExitStack() as stack:
        policy_client = stack.enter_context(
            httpx.Client(
                headers=headers,
                timeout=15,
                follow_redirects=True,
                event_hooks={"request": [_guard_http_request]},
            )
        )
        playwright = stack.enter_context(sync_playwright())
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=config.profile.browser_user_agent,
            viewport={
                "width": config.profile.viewport_width,
                "height": config.profile.viewport_height,
            },
            is_mobile=config.profile.is_mobile,
            has_touch=config.profile.has_touch,
            java_script_enabled=config.js_rendering,
            ignore_https_errors=False,
            service_workers="block",
        )

        navigation_block: _NavigationBlock | None = None

        def remember_navigation_block(block: _NavigationBlock) -> None:
            nonlocal navigation_block
            navigation_block = block

        def route_request(route: Route, request: Request) -> None:
            _route_browser_request(
                route,
                request,
                scope_key=frontier.scope_key,
                policy_client=policy_client,
                robots_cache=robots_cache,
                robots_user_agent=config.profile.robots_user_agent,
                max_robots_bytes=config.max_robots_bytes,
                host_allow_cache=host_allow_cache,
                on_navigation_blocked=remember_navigation_block,
            )

        context.route("**/*", route_request)
        page = context.new_page()

        def recycle_page() -> None:
            """Replace the page a failed navigation left behind.

            ``page.goto`` timing out raises here but does **not** cancel the
            navigation — Chromium keeps fetching that URL. Reusing the page then
            lets the straggler arrive mid-flight and abort the *next* goto, so
            one slow page becomes a chain of failures ("interrupted by another
            navigation"), and every unfinished load stays outstanding against a
            target that has already stopped answering. Closing the page cancels
            its inflight work. The route handler is registered on the *context*,
            so the replacement page is governed identically.
            """

            nonlocal page
            try:
                page.close()
            except Exception:
                # A page that will not close is already unusable; the
                # replacement is the part that matters and the browser reaps it.
                logger.warning("Site Audit could not close the page after a failed navigation")
            page = context.new_page()

        consecutive_failures = 0

        try:
            while frontier.queue and processed < config.page_limit:
                current_url = frontier.queue.popleft()
                current_robots = _robots_for_url(
                    policy_client,
                    robots_cache,
                    current_url,
                    config.profile.robots_user_agent,
                    config.max_robots_bytes,
                )
                if not current_robots.safely_read:
                    crawled = CrawledPage(
                        requested_url=current_url,
                        final_url=current_url,
                        status_code=0,
                        error=_robots_failure_message(current_robots),
                    )
                    on_page(crawled, len(frontier.visited))
                    processed += 1
                    continue
                if not current_robots.policy.allows(
                    config.profile.robots_user_agent,
                    current_url,
                ):
                    crawled = CrawledPage(
                        requested_url=current_url,
                        final_url=current_url,
                        status_code=0,
                        blocked_by_robots=True,
                    )
                    on_page(crawled, len(frontier.visited))
                    processed += 1
                    continue

                navigation_block = None
                try:
                    response = page.goto(
                        current_url,
                        wait_until="domcontentloaded",
                        timeout=config.page_timeout_ms,
                    )
                    if response is None:
                        raise RuntimeError("browser returned no HTTP response")

                    final_url = normalize_crawl_url(page.url) or current_url
                    if not _same_scope(final_url, frontier.scope_key):
                        raise UnsafeCrawlTarget("redirect left the SEO project domain")
                    response_headers = dict(response.headers)
                    if not _is_html_response(response_headers):
                        consecutive_failures = 0
                        processed += 1
                        delay = max(
                            config.crawl_delay_seconds,
                            current_robots.policy.crawl_delay_seconds,
                        )
                        if delay:
                            time.sleep(delay)
                        continue

                    try:
                        raw_html = response.text()
                    except Exception:
                        raw_html = ""
                    raw_html = raw_html[: config.max_html_chars]

                    rendered_html: str | None = None
                    if config.js_rendering:
                        page.wait_for_timeout(config.render_wait_ms)
                        rendered_html = page.content()[: config.max_html_chars]

                    discovered_links = extract_links(raw_html, final_url)
                    if rendered_html is not None:
                        discovered_links.extend(extract_links(rendered_html, final_url))
                    before_count = len(frontier.visited)
                    for discovered_link in dict.fromkeys(discovered_links):
                        frontier.add(discovered_link)
                    if on_discovery is not None and len(frontier.visited) != before_count:
                        on_discovery(len(frontier.visited))

                    crawled = CrawledPage(
                        requested_url=current_url,
                        final_url=final_url,
                        status_code=response.status,
                        raw_html=raw_html,
                        rendered_html=rendered_html,
                        response_headers=response_headers,
                    )
                    consecutive_failures = 0
                except Exception as exc:
                    # Read before recycling: closing the page can still fire a
                    # pending route callback, and that would rewrite the block
                    # this iteration is supposed to be reporting.
                    blocked = navigation_block
                    recycle_page()
                    if blocked is not None:
                        # This navigation was aborted by our own robots policy,
                        # not by the target failing to answer. It is an outcome,
                        # so it must drive neither the backoff nor the stop —
                        # otherwise a run of disallowed redirects would look
                        # exactly like a site that had gone silent.
                        consecutive_failures = 0
                        if blocked.robots.safely_read:
                            crawled = CrawledPage(
                                requested_url=current_url,
                                final_url=blocked.url,
                                status_code=0,
                                blocked_by_robots=True,
                            )
                        else:
                            crawled = CrawledPage(
                                requested_url=current_url,
                                final_url=blocked.url,
                                status_code=0,
                                error=_robots_failure_message(blocked.robots),
                            )
                    else:
                        consecutive_failures += 1
                        logger.warning(
                            "Site Audit navigation failed (%s in a row) for %s: %s",
                            consecutive_failures,
                            current_url,
                            (str(exc) or exc.__class__.__name__).splitlines()[0],
                        )
                        crawled = CrawledPage(
                            requested_url=current_url,
                            final_url=current_url,
                            status_code=0,
                            error=str(exc)[:500],
                        )

                on_page(crawled, len(frontier.visited))
                processed += 1

                if (
                    config.max_consecutive_failures
                    and consecutive_failures >= config.max_consecutive_failures
                ):
                    # The remaining budget would buy nothing but timeouts, and
                    # spending it keeps loading a site that stopped answering.
                    logger.warning(
                        "Site Audit stopped after %s consecutive navigation failures; "
                        "%s of %s pages processed",
                        consecutive_failures,
                        processed,
                        config.page_limit,
                    )
                    break

                delay = _next_delay_seconds(
                    max(
                        config.crawl_delay_seconds,
                        current_robots.policy.crawl_delay_seconds,
                    ),
                    consecutive_failures,
                    config.failure_backoff_max_seconds,
                )
                if delay:
                    time.sleep(delay)
        finally:
            context.close()
            browser.close()

    return processed
