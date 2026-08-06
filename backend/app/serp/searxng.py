"""SearXNG — the open-source metasearch instance Yanki reads SERPs from.

SearXNG (AGPL-3.0, <https://github.com/searxng/searxng>) puts the public search
engines behind one self-hostable JSON API. It is the source here because the two
alternatives both cost us something we are not willing to spend: a commercial
SERP API bills per query, which is a per-analysis invoice sitting in front of the
"affordable, transparent" wedge, and scraping Google ourselves is a blocklist
maintenance project, not a feature. A container the operator already controls is
neither.

The instance must have the JSON format switched on — it is **off by default**::

    # settings.yml
    search:
      formats: [html, json]

Response shape, verified against a live 2026.8 instance rather than the docs
(which do not publish the schema)::

    {"query": "...",
     "results": [{"url", "title", "content", "engine", "engines", "positions",
                  "score", "category", "template", "parsed_url", ...}],
     "answers": [], "corrections": [], "infoboxes": [], "suggestions": [],
     "unresponsive_engines": [["brave", "Suspended: too many requests"], ...]}

Every field is read defensively, and a missing one degrades to an empty string
rather than raising: instances run whatever SearXNG version their operator
pulled, and this code runs inside the worker, where an unexpected key must not
become a failed analysis. ``number_of_results`` is deliberately not read — the
live instance returns ``null`` for it.

**No SSRF guard here, and that is deliberate.** ``net_guard`` exists because
discovery fetches a URL an anonymous stranger submitted. This base URL is the
operator's own configuration, and the intended deployment is a sidecar on the
compose network (``http://searxng:8080``) — precisely the private address space
the guard rejects. Guarding it would break every correct deployment while
protecting nothing: whoever sets ``SERP_BASE_URL`` already sets
``DATABASE_URL``.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.serp.base import SerpPage, SerpResult, SerpUnavailable

USER_AGENT = "YankiBot/0.1"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_RESULTS = 20

# Snippets are stored per query, so cap what one result may contribute. A
# SearXNG snippet is normally two lines; anything far past that is a page that
# put its whole body in a meta description.
MAX_URL_CHARS = 2_000
MAX_TITLE_CHARS = 300
MAX_CONTENT_CHARS = 1_000


def _text(value: object, limit: int) -> str:
    """One string field, whitespace-collapsed and capped; ``""`` for anything else."""
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit]


def _engine_of(entry: dict[str, Any]) -> str:
    """Which engine produced a result: ``engine``, else the first of ``engines``."""
    engine = _text(entry.get("engine"), 60)
    if engine:
        return engine
    engines = entry.get("engines")
    if isinstance(engines, list):
        for candidate in engines:
            name = _text(candidate, 60)
            if name:
                return name
    return ""


def _unresponsive(payload: dict[str, Any]) -> list[str]:
    """Engine names that failed to answer.

    The live shape is a list of ``[name, reason]`` pairs, but the field has
    carried bare strings and objects across versions, so all three are accepted.
    Only the name is kept: the reason ("CAPTCHA", "Suspended: too many
    requests") is upstream's business, and what this code needs to know is
    simply that the engine did not contribute.
    """
    raw = payload.get("unresponsive_engines")
    if not isinstance(raw, list):
        return []
    names: list[str] = []
    for entry in raw:
        name = ""
        if isinstance(entry, str):
            name = _text(entry, 60)
        elif isinstance(entry, list | tuple) and entry:
            name = _text(entry[0], 60)
        elif isinstance(entry, dict):
            name = _text(entry.get("name") or entry.get("engine"), 60)
        if name and name not in names:
            names.append(name)
    return names


def _suggestions(payload: dict[str, Any]) -> list[str]:
    """Autocomplete-style suggestions from a SearXNG JSON payload."""
    raw = payload.get("suggestions")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for entry in raw:
        text = _text(entry, MAX_TITLE_CHARS)
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


class SearxngSource:
    """Reads one SERP per query from a SearXNG instance's JSON API."""

    name = "searxng"

    def __init__(
        self,
        base_url: str,
        *,
        language: str = "en",
        categories: str = "general",
        engines: str = "",
        safesearch: int = 0,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_results: int = DEFAULT_MAX_RESULTS,
    ) -> None:
        self.base_url = (base_url or "").strip().rstrip("/")
        self.language = (language or "en").strip() or "en"
        self.categories = (categories or "general").strip() or "general"
        self.engines = (engines or "").strip()
        self.safesearch = safesearch
        self.timeout_seconds = timeout_seconds
        self.max_results = max(1, max_results)

    def _params(self, query: str) -> dict[str, str | int]:
        """Query parameters for ``/search``.

        ``language`` is pinned rather than left to the instance because a
        metasearch instance geolocates by its own egress IP: the same query from
        a German-hosted container answers in German, which would silently make
        one deployment's numbers incomparable with another's.
        """
        params: dict[str, str | int] = {
            "q": query,
            "format": "json",
            "pageno": 1,
            "language": self.language,
            "categories": self.categories,
            "safesearch": self.safesearch,
        }
        if self.engines:
            params["engines"] = self.engines
        return params

    def _results(self, payload: dict[str, Any]) -> list[SerpResult]:
        raw = payload.get("results")
        if not isinstance(raw, list):
            return []
        results: list[SerpResult] = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            url = _text(entry.get("url"), MAX_URL_CHARS)
            if not url:
                continue
            results.append(
                SerpResult(
                    rank=len(results) + 1,
                    url=url,
                    title=_text(entry.get("title"), MAX_TITLE_CHARS),
                    content=_text(entry.get("content"), MAX_CONTENT_CHARS),
                    engine=_engine_of(entry),
                )
            )
            if len(results) >= self.max_results:
                break
        return results

    def search(self, query: str) -> SerpPage:
        if not self.base_url:
            raise SerpUnavailable("no SearXNG base URL is configured")
        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
            ) as client:
                response = client.get(f"{self.base_url}/search", params=self._params(query))
        except httpx.HTTPError as exc:
            raise SerpUnavailable(f"could not reach the search instance: {exc}") from exc

        if response.status_code != 200:
            # 403 is the one worth recognising by sight: it is what an instance
            # with its limiter on returns to a bot-shaped client, and it means
            # "configure the instance", not "the network is down".
            raise SerpUnavailable(f"the search instance answered {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            # Almost always the JSON format not being enabled: the instance
            # cheerfully serves the HTML results page instead.
            raise SerpUnavailable("the search instance did not return JSON") from exc
        if not isinstance(payload, dict):
            raise SerpUnavailable("the search instance returned an unexpected payload")

        return SerpPage(
            query=query,
            results=tuple(self._results(payload)),
            unresponsive_engines=tuple(_unresponsive(payload)),
            suggestions=tuple(_suggestions(payload)),
        )
