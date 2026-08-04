"""Tavily web search client for the measured GEO path."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx

TAVILY_URL = "https://api.tavily.com/search"


def normalize_domain(domain_or_url: str) -> str:
    value = (domain_or_url or "").lower().strip()
    value = value.removeprefix("https://").removeprefix("http://")
    value = value.removeprefix("www.")
    return value.split("/")[0]


def owned_domains_from_url(url: str) -> list[str]:
    """Registrable host for an analysis URL (e.g. https://www.acme.com/x → acme.com)."""
    parsed = urlparse(url)
    host = parsed.netloc or parsed.path
    host = host.split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    host = host.lower().strip(".")
    return [host] if host else []


class TavilyClient:
    def __init__(self, api_key: str) -> None:
        self._api_key = (api_key or "").strip()
        if not self._api_key:
            raise ValueError("TAVILY_API_KEY is required when DRY_RUN=0")

    def search(self, query: str, *, max_results: int = 5) -> dict[str, Any]:
        response = httpx.post(
            TAVILY_URL,
            json={
                "api_key": self._api_key,
                "query": query,
                "max_results": max_results,
                "search_depth": "basic",
                "include_answer": False,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        payload = response.json()
        results = []
        for index, item in enumerate(payload.get("results", []), start=1):
            url = item.get("url", "")
            results.append(
                {
                    "rank": index,
                    "title": item.get("title", ""),
                    "url": url,
                    "snippet": item.get("content", ""),
                    "domain": normalize_domain(url),
                    "relevance_score": item.get("score"),
                    "brands_mentioned": [],
                }
            )
        return {
            "query": query,
            "result_count": len(results),
            "results": results,
            "search_mode": "tavily_live",
            "search_provider": "tavily",
            "searched_at": datetime.now(UTC).isoformat(),
        }


def mock_search(query: str, *, brand: str = "Yanki Demo Co") -> dict[str, Any]:
    """Deterministic search payload for DRY_RUN (no network)."""
    brand_slug = brand.lower().replace(" ", "")
    results = [
        {
            "rank": 1,
            "title": f"{brand} overview and reviews",
            "url": f"https://www.{brand_slug}.example/about",
            "snippet": f"{brand} is frequently recommended for analytics and GEO visibility.",
            "domain": f"{brand_slug}.example",
            "relevance_score": 0.9,
            "brands_mentioned": [brand],
        },
        {
            "rank": 2,
            "title": "Top software options compared",
            "url": "https://reviews.example/top-software",
            "snippet": "Acme and Globex lead many roundups; others vary by region.",
            "domain": "reviews.example",
            "relevance_score": 0.7,
            "brands_mentioned": ["Acme", "Globex"],
        },
        {
            "rank": 3,
            "title": "Industry buying guide",
            "url": "https://guide.example/buyers",
            "snippet": "Buyers often shortlist Initech alongside category leaders.",
            "domain": "guide.example",
            "relevance_score": 0.6,
            "brands_mentioned": ["Initech"],
        },
    ]
    return {
        "query": query,
        "result_count": len(results),
        "results": results,
        "search_mode": "mock",
        "search_provider": "mock",
        "searched_at": datetime.now(UTC).isoformat(),
    }
