"""DataForSEO Google Organic SERP — commercial SERP source (ADR-28 successor).

Uses the Live Advanced endpoint:
``POST /v3/serp/google/organic/live/advanced``

Maps organic rows to :class:`SerpResult`, ``related_searches`` → suggestions,
``people_also_ask`` question titles → answers. Unlike SearXNG there is no
``unresponsive_engines`` panel — an empty organic list is a measurable empty SERP.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.serp.base import SerpPage, SerpResult, SerpUnavailable

USER_AGENT = "YankiBot/0.1"
# Live Advanced often exceeds 10s (especially from Docker). SearXNG defaults stay lower.
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_RESULTS = 20
DEFAULT_LOCATION_CODE = 2840  # United States
DEFAULT_DEVICE = "desktop"

API_URL = "https://api.dataforseo.com/v3/serp/google/organic/live/advanced"
OK_STATUS = 20000

MAX_URL_CHARS = 2_000
MAX_TITLE_CHARS = 300
MAX_CONTENT_CHARS = 1_000

# ``serp_language`` → DataForSEO location_code (first slice; override via settings).
_LANGUAGE_LOCATION: dict[str, int] = {
    "en": 2840,
    "en-us": 2840,
    "en-gb": 2826,
    "tr": 2792,
    "de": 2276,
    "fr": 2250,
}


def _text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit]


def location_code_for_language(language: str, *, override: int | None = None) -> int:
    if override is not None and override > 0:
        return override
    key = (language or "en").strip().lower().replace("_", "-")
    if key in _LANGUAGE_LOCATION:
        return _LANGUAGE_LOCATION[key]
    base = key.split("-", 1)[0]
    return _LANGUAGE_LOCATION.get(base, DEFAULT_LOCATION_CODE)


def _api_error_message(payload: dict[str, Any]) -> str:
    code = payload.get("status_code")
    message = payload.get("status_message")
    if code is not None and message:
        return f"DataForSEO answered {code}: {message}"
    return "DataForSEO returned an error"


def _task_result_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise SerpUnavailable("DataForSEO returned no tasks")
    task = tasks[0]
    if not isinstance(task, dict):
        raise SerpUnavailable("DataForSEO task payload was malformed")
    task_status = task.get("status_code")
    if task_status != OK_STATUS:
        msg = task.get("status_message") or _api_error_message(payload)
        raise SerpUnavailable(str(msg))
    results = task.get("result")
    if not isinstance(results, list) or not results:
        return []
    first = results[0]
    if not isinstance(first, dict):
        return []
    items = first.get("items")
    if not isinstance(items, list):
        return []
    return [entry for entry in items if isinstance(entry, dict)]


def _organic_results(items: list[dict[str, Any]], *, max_results: int) -> list[SerpResult]:
    results: list[SerpResult] = []
    for entry in items:
        if entry.get("type") != "organic":
            continue
        url = _text(entry.get("url"), MAX_URL_CHARS)
        if not url:
            continue
        results.append(
            SerpResult(
                rank=len(results) + 1,
                url=url,
                title=_text(entry.get("title"), MAX_TITLE_CHARS),
                content=_text(entry.get("description"), MAX_CONTENT_CHARS),
                engine="google",
            )
        )
        if len(results) >= max_results:
            break
    return results


def _related_search_suggestions(items: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for entry in items:
        if entry.get("type") != "related_searches":
            continue
        related = entry.get("items")
        if not isinstance(related, list):
            continue
        for raw in related:
            if isinstance(raw, str):
                text = _text(raw, 120)
            elif isinstance(raw, dict):
                text = _text(raw.get("title"), 120)
            else:
                text = ""
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(text)
    return out


def _people_also_ask_strings(items: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for entry in items:
        if entry.get("type") != "people_also_ask":
            continue
        paa_items = entry.get("items")
        if not isinstance(paa_items, list):
            continue
        for block in paa_items:
            if not isinstance(block, dict):
                continue
            text = _text(block.get("title"), 200)
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(text)
    return out


def page_from_api_payload(payload: dict[str, Any], *, query: str, max_results: int) -> SerpPage:
    """Parse a full DataForSEO live/advanced JSON response into a :class:`SerpPage`."""
    if payload.get("status_code") != OK_STATUS:
        raise SerpUnavailable(_api_error_message(payload))
    items = _task_result_items(payload)
    return SerpPage(
        query=query,
        results=tuple(_organic_results(items, max_results=max_results)),
        unresponsive_engines=(),
        suggestions=tuple(_related_search_suggestions(items)),
        answers=tuple(_people_also_ask_strings(items)),
    )


class DataForSeoSource:
    """Reads one organic Google SERP per query via DataForSEO Live Advanced API."""

    name = "dataforseo"

    def __init__(
        self,
        login: str,
        password: str,
        *,
        language: str = "en",
        location_code: int | None = None,
        device: str = DEFAULT_DEVICE,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_results: int = DEFAULT_MAX_RESULTS,
    ) -> None:
        self.login = (login or "").strip()
        self.password = (password or "").strip()
        self.language = (language or "en").strip() or "en"
        self.location_code = location_code_for_language(self.language, override=location_code)
        self.device = (device or DEFAULT_DEVICE).strip() or DEFAULT_DEVICE
        self.timeout_seconds = timeout_seconds
        self.max_results = max(1, max_results)

    def _task_body(self, query: str) -> list[dict[str, Any]]:
        depth = min(self.max_results, 200)
        return [
            {
                "keyword": query,
                "language_code": self.language.split("-", 1)[0],
                "location_code": self.location_code,
                "device": self.device,
                "depth": depth,
            }
        ]

    def search(self, query: str) -> SerpPage:
        if not self.login or not self.password:
            raise SerpUnavailable("DataForSEO credentials are not configured")
        try:
            timeout = httpx.Timeout(
                connect=10.0,
                read=self.timeout_seconds,
                write=10.0,
                pool=10.0,
            )
            with httpx.Client(
                timeout=timeout,
                headers={"User-Agent": USER_AGENT},
            ) as client:
                response = client.post(
                    API_URL,
                    json=self._task_body(query),
                    auth=(self.login, self.password),
                )
        except (httpx.HTTPError, OSError) as exc:
            raise SerpUnavailable(f"could not reach DataForSEO: {exc}") from exc

        if response.status_code == 401:
            raise SerpUnavailable("DataForSEO rejected the credentials")
        if response.status_code != 200:
            raise SerpUnavailable(f"DataForSEO answered HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise SerpUnavailable("DataForSEO did not return JSON") from exc
        if not isinstance(payload, dict):
            raise SerpUnavailable("DataForSEO returned an unexpected payload")
        return page_from_api_payload(payload, query=query, max_results=self.max_results)
