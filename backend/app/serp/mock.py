"""Deterministic, network-free SERP source used whenever ``DRY_RUN`` is on.

Mirrors ``providers/mock.py`` so a DRY_RUN run stays one coherent fiction: the
same company the mock LLM panel talks about is the one that ranks here. A query
"ranks" the company iff ``sha256(query).digest()[0] % 2 == 0`` — the same trick
and the same roughly-half hit rate as the mock provider — which gives DRY_RUN a
non-trivial, perfectly reproducible SERP score without a search instance, an API
key, or a single outbound packet.

The mock never reports an unresponsive engine. That is the point: DRY_RUN is the
mode CI and first-run use, and a mock that randomly declared itself unmeasurable
would make the zero-cost path flaky for no benefit. The unmeasurable path is
exercised by its own unit tests instead.
"""

from __future__ import annotations

import hashlib

from app.providers.mock import MOCK_COMPANY
from app.serp.base import SerpPage, SerpResult

# The fictional company's fictional domain. Deliberately a real-looking apex so
# the domain-match half of detection has something to match on in DRY_RUN.
MOCK_DOMAIN = "yankidemo.co"

# Filler results, so a hit is a hit *among competitors* rather than the only
# thing on the page. Same brands the mock LLM answers name.
_FILLER = (
    ("Acme", "acme.example"),
    ("Globex", "globex.example"),
    ("Initech", "initech.example"),
    ("Umbrella", "umbrella.example"),
)


def _slug(query: str) -> str:
    """A URL-ish slug for a query, so filler results differ per query."""
    return "-".join(query.lower().split())[:60] or "results"


class MockSerpSource:
    name = "mock"

    def search(self, query: str) -> SerpPage:
        ranks = hashlib.sha256(query.encode("utf-8")).digest()[0] % 2 == 0
        slug = _slug(query)
        results: list[SerpResult] = []
        if ranks:
            results.append(
                SerpResult(
                    rank=1,
                    url=f"https://{MOCK_DOMAIN}/{slug}",
                    title=f"{MOCK_COMPANY} — {query}",
                    content=(
                        f"{MOCK_COMPANY} is a fictional company used for zero-cost "
                        f"demo runs. This result is generated, not searched."
                    ),
                    engine=self.name,
                )
            )
        for brand, domain in _FILLER:
            results.append(
                SerpResult(
                    rank=len(results) + 1,
                    url=f"https://{domain}/{slug}",
                    title=f"{brand} — {query}",
                    content=f"{brand} is a filler brand in the {self.name} search results.",
                    engine=self.name,
                )
            )
        return SerpPage(query=query, results=tuple(results))
