"""On-demand domain rank checks for selected keyword queries (preview).

Reuses the configured :class:`~app.serp.base.SerpSource` (SearXNG or DataForSEO)
and host matching from ``serp_visibility``. Text/brand snippet hits are out of
scope — only own-domain / subdomain matches count. Budget is small (default 10
queries) to protect the operator's SERP politeness budget.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from app.keyword.normalize import collapse_keyword_whitespace
from app.pipeline.serp_visibility import site_hosts
from app.serp.base import SerpPage, SerpSource, SerpUnavailable

DEFAULT_RANK_QUERY_BUDGET = 10
# DataForSEO Live calls are slow; parallelize a small fan-out to stay under proxy limits.
MAX_RANK_CHECK_WORKERS = 5


def _unmeasurable_hit(query: str) -> KeywordRankHit:
    return KeywordRankHit(
        query=query,
        measurable=False,
        appeared=None,
        rank=None,
        matched_url=None,
        matched_via=None,
    )


@dataclass(frozen=True)
class KeywordRankHit:
    query: str
    measurable: bool
    appeared: bool | None
    rank: int | None
    matched_url: str | None
    matched_via: str | None


def _rank_hit_for_query(
    source: SerpSource,
    query: str,
    hosts: frozenset[str],
) -> KeywordRankHit:
    try:
        page = source.search(query)
    except SerpUnavailable:
        return _unmeasurable_hit(query)
    except Exception:
        # One bad query must not 500 the whole batch (live API flakiness).
        return _unmeasurable_hit(query)
    if not page.measurable:
        return _unmeasurable_hit(query)
    match = _domain_hit(page, hosts)
    if match is None:
        return KeywordRankHit(
            query=query,
            measurable=True,
            appeared=False,
            rank=None,
            matched_url=None,
            matched_via=None,
        )
    rank, url = match
    return KeywordRankHit(
        query=query,
        measurable=True,
        appeared=True,
        rank=rank,
        matched_url=url,
        matched_via="domain",
    )


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

    language = (locale or "en").strip() or "en"
    previous_language = getattr(source, "language", None)
    previous_location = getattr(source, "location_code", None)
    if hasattr(source, "language"):
        source.language = language  # type: ignore[attr-defined]
    if hasattr(source, "location_code"):
        from app.serp.dataforseo import location_code_for_language

        source.location_code = location_code_for_language(language)  # type: ignore[attr-defined]

    hits: list[KeywordRankHit] = []
    try:
        if len(cleaned_queries) <= 1:
            hits = [_rank_hit_for_query(source, query, hosts) for query in cleaned_queries]
        else:
            workers = min(MAX_RANK_CHECK_WORKERS, len(cleaned_queries))
            with ThreadPoolExecutor(max_workers=workers) as executor:
                hits = list(
                    executor.map(
                        lambda query: _rank_hit_for_query(source, query, hosts),
                        cleaned_queries,
                    )
                )
    finally:
        if hasattr(source, "language") and isinstance(previous_language, str):
            source.language = previous_language  # type: ignore[attr-defined]
        if hasattr(source, "location_code") and previous_location is not None:
            source.location_code = previous_location  # type: ignore[attr-defined]

    return host, hits
