"""OpenRouter chat-completions client for KYC + measured audit LLM calls.

All production LLM traffic for the measured GEO path goes through OpenRouter
(``OPEN_ROUTER_KEY`` / ``OPENROUTER_MODEL``). Under ``DRY_RUN`` the registry
returns a mock instead of this client.
"""

from __future__ import annotations

import httpx

from app.providers.base import ProviderResult

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MAX_TOKENS = 3500
DEFAULT_TEMPERATURE = 0.2


class OpenRouterProvider:
    """Thin OpenAI-compatible chat client against OpenRouter."""

    name = "openrouter"

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = (api_key or "").strip()
        self.model = model
        if not self._api_key:
            raise ValueError("OPEN_ROUTER_KEY is required when DRY_RUN=0")

    def generate(self, prompt: str) -> ProviderResult:
        """Single-user-message completion (KYC JSON and simple prompts)."""
        return self.chat(
            [{"role": "user", "content": prompt}],
            temperature=DEFAULT_TEMPERATURE,
            max_tokens=1024,
            json_object=True,
        )

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        json_object: bool = True,
    ) -> ProviderResult:
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_object:
            payload["response_format"] = {"type": "json_object"}

        response = httpx.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=90.0,
        )
        response.raise_for_status()
        data = response.json()
        if "choices" not in data:
            raise RuntimeError(f"OpenRouter response missing choices: {data}")

        text = data["choices"][0]["message"]["content"] or ""
        usage = data.get("usage") or {}
        # OpenRouter may report native cost; fall back to 0 when absent.
        cost = float(usage.get("cost") or data.get("cost") or 0.0)
        return ProviderResult(text=text, model=self.model, cost_usd=round(cost, 6))
