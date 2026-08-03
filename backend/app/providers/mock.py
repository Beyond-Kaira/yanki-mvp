"""Deterministic, $0 provider used whenever ``DRY_RUN`` is on.

In DRY_RUN the whole pipeline runs on a single fictional company so the demo is
free and fully reproducible. The same mock serves two kinds of prompt:

* the KYC step asks for a JSON company profile — the mock returns a canned,
  valid profile for :data:`MOCK_COMPANY`;
* the execution step asks recommendation-style questions — the mock mentions the
  company iff ``sha256(prompt).digest()[0] % 2 == 0`` (so roughly half of the
  answers count as a footprint), otherwise it names only filler brands.
"""

from __future__ import annotations

import hashlib
import json

from app.providers.base import ProviderResult

# The fictional company the whole DRY_RUN pipeline is about.
MOCK_COMPANY = "Yanki Demo Co"

_FILLER_BRANDS = ["Acme", "Globex", "Initech", "Umbrella", "Stark"]

# A valid KYC profile the mock returns for the KYC step (see kyc.build_prompt,
# which always contains the words "JSON object").
_KYC_PROFILE = {
    "company": MOCK_COMPANY,
    "description": "A fictional company used for zero-cost demo runs.",
    "industry": "Software",
    # The buyer-facing category and use cases the real prompt asks for, so a
    # DRY_RUN run exercises the same fields prompt generation prefers.
    "category": "AI visibility tools",
    "aliases": [MOCK_COMPANY, "Yanki"],
    "products": ["Demo Platform", "Insights API"],
    "services": ["Consulting"],
    "keywords": ["analytics", "geo", "visibility"],
    "use_cases": ["brand visibility tracking", "AI answer monitoring"],
    "locations": ["Istanbul"],
    "competitors": ["Acme", "Globex"],
}


class MockProvider:
    model = "mock"

    def __init__(self, engine: str) -> None:
        self.name = engine

    def generate(self, prompt: str) -> ProviderResult:
        if "json object" in prompt.lower():
            return ProviderResult(
                text=json.dumps(_KYC_PROFILE), model=self.model, cost_usd=0.0
            )

        mentions = hashlib.sha256(prompt.encode("utf-8")).digest()[0] % 2 == 0
        brands = ", ".join(_FILLER_BRANDS)
        if mentions:
            text = (
                f"For this I would recommend {MOCK_COMPANY}. Other options in "
                f"the market include {brands}. (answer from the {self.name} "
                f"mock engine)"
            )
        else:
            text = (
                f"Some well-known options here include {brands}. "
                f"(answer from the {self.name} mock engine)"
            )
        return ProviderResult(text=text, model=self.model, cost_usd=0.0)
