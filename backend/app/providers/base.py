"""The provider interface every engine adapter implements.

Every adapter exposes ``name`` (the panel engine name), ``model`` (the model
string recorded on each response) and a single ``generate(prompt)`` call that
returns a :class:`ProviderResult`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol, runtime_checkable


@dataclass
class ProviderResult:
    """The output of one provider call."""

    text: str
    model: str
    cost_usd: float


class UsageTrackingProvider:
    """Transparent provider wrapper that keeps successful call-level spend.

    Response rows account for the prompt panel, but KYC happens before those
    rows exist.  Wrapping that provider lets the runner persist the otherwise
    invisible call (including the bounded JSON-repair retry) without changing
    the long-standing ``generate_kyc`` return type.
    """

    def __init__(self, provider: Provider) -> None:
        self._provider = provider
        self.name = provider.name
        self.model = provider.model
        self.usage: list[dict[str, str]] = []

    def generate(self, prompt: str) -> ProviderResult:
        result = self._provider.generate(prompt)
        cost = Decimal(str(result.cost_usd or 0))
        if cost < 0:
            cost = Decimal("0")
        cost = cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        self.usage.append(
            {
                "provider": self.name,
                "model": result.model,
                "stage": "kyc",
                "cost_usd": str(cost),
            }
        )
        return result

    @property
    def cost_usd(self) -> Decimal:
        return sum(
            (Decimal(item["cost_usd"]) for item in self.usage),
            start=Decimal("0"),
        )


@runtime_checkable
class Provider(Protocol):
    name: str
    model: str

    def generate(self, prompt: str) -> ProviderResult: ...
