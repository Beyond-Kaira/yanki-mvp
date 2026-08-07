"""On-demand domain rank checks for selected keyword queries (preview).

Reuses SearXNG via ``SerpSource`` and host matching from ``serp_visibility``.
Text/brand snippet hits are out of scope here — only own-domain / subdomain
matches count. Budget is small (default 10 queries) to protect the instance.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.keyword.normalize import collapse_keyword_whitespace
from app.pipeline.serp_visibility import site_hosts
from app.serp.base import SerpPage, SerpSource, SerpUnavailable

DEFAULT_RANK_QUERY_BUDGET = 10


@dataclass(frozen=True)
class KeywordRankHit:
    query: str
    measurable: bool
    appeared: bool | None
    rank: int | None
    matched_url: str | None
    matched_via: str | None


def _domain_hit(page: SerpPage, hosts: frozenset[str]) -> tuple[int, str] | None:
    """First own-site result (rank, url), or None."""
    if not hosts:
        return None
    for result in page.results:
        host = ""
        try:
            from urllib.parse import urlparse

            parsed = urlparse(result.url)
            host = (parsed.hostname or "").strip().lower()
            if host.startswith("www."):
                host = host[4:]
        except ValueError:
            continue
        if any(host == owned or host.endswith(f".{owned}") for owned in hosts):
            return result.rank, result.url
    return None


def normalize_rank_domain(domain: str) -> str:
    """Accept bare host or URL; return comparison host or \"\"."""
    cleaned = collapse_keyword_whitespace(domain)
    if not cleaned:
        return ""
    if "://" not in cleaned:
        cleaned = f"https://{cleaned}"
    hosts = site_hosts(cleaned)
    return next(iter(hosts), "")


def check_keyword_ranks(
    source: SerpSource,
    *,
    domain: str,
    queries: list[str],
    locale: str = "en",
    max_queries: int = DEFAULT_RANK_QUERY_BUDGET,
) -> tuple[str, list[KeywordRankHit]]:
    """Run up to ``max_queries`` SERP lookups; return (normalized_domain, hits)."""
    host = normalize_rank_domain(domain)
    if not host:
        raise ValueError("domain must be a http(s) host")

    hosts = frozenset({host})
    cleaned_queries: list[str] = []
    seen: set[str] = set()
    for raw in queries:
        phrase = collapse_keyword_whitespace(raw)
        key = phrase.lower()
        if not phrase or key in seen:
            continue
        seen.add(key)
        cleaned_queries.append(phrase)
        if len(cleaned_queries) >= max(1, max_queries):
            break

    # Locale maps onto SearXNG language when the source supports it.
    previous = getattr(source, "language", None)
    if previous is not None and hasattr(source, "language"):
        source.language = (locale or "en").strip() or "en"  # type: ignore[attr-defined]

    hits: list[KeywordRankHit] = []
    try:
        for query in cleaned_queries:
            try:
                page = source.search(query)
            except SerpUnavailable:
                hits.append(
                    KeywordRankHit(
                        query=query,
                        measurable=False,
                        appeared=None,
                        rank=None,
                        matched_url=None,
                        matched_via=None,
                    )
                )
                continue
            if not page.measurable:
                hits.append(
                    KeywordRankHit(
                        query=query,
                        measurable=False,
                        appeared=None,
                        rank=None,
                        matched_url=None,
                        matched_via=None,
                    )
                )
                continue
            match = _domain_hit(page, hosts)
            if match is None:
                hits.append(
                    KeywordRankHit(
                        query=query,
                        measurable=True,
                        appeared=False,
                        rank=None,
                        matched_url=None,
                        matched_via=None,
                    )
                )
            else:
                rank, url = match
                hits.append(
                    KeywordRankHit(
                        query=query,
                        measurable=True,
                        appeared=True,
                        rank=rank,
                        matched_url=url,
                        matched_via="domain",
                    )
                )
    finally:
        if previous is not None and hasattr(source, "language"):
            source.language = previous  # type: ignore[attr-defined]

    return host, hits
