"""Application settings, loaded from environment variables (12-factor style).

Every value has a safe default so the app boots with zero configuration. The most
important default is ``dry_run=True``: out of the box the pipeline runs on the
deterministic mock provider and spends $0.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+psycopg://yanki:yanki@localhost:5432/yanki"

    # Provider credentials (blank in DRY_RUN)
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    perplexity_api_key: str = ""
    # Measured / simulated GEO path (OpenRouter LLM + optional Tavily search).
    # Required when dry_run=False; ignored under dry_run. Keep blanks in source —
    # set real values only in deploy/.env (gitignored).
    open_router_key: str = ""
    tavily_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o-mini"
    # measured = Tavily + grounded answer; simulated = OpenRouter-only SYSTEM_PROMPT
    geo_mode: str = "measured"

    # Pipeline behaviour
    dry_run: bool = True
    prompt_count: int = 10
    panel_engines: str = "anthropic,openai,gemini,perplexity"
    max_responses_per_job: int = 60

    # Worker / queue
    worker_poll_seconds: int = 2
    stale_claim_seconds: int = 300

    # Rate limiting (P5.0) — the LIVE POST /api/v1/analyses is public with real
    # keys; these guard it before any row is created or money is spent.
    analyses_rate_limit_per_ip_hour: int = 5
    analyses_daily_cap: int = 100
    ip_hash_salt: str = ""

    # Checker (P5.1) — a fresh checker run is reused for this many hours when a
    # done analysis with the same normalized (brand, category, lang) exists, so
    # a hot brand costs $0 on repeat and can't be hammered into new LLM spend.
    checker_result_cache_hours: int = 24

    # Checker public hardening (P5.6) — POST /api/v1/checker is the anonymous,
    # LLM-spending public endpoint. Every guard below runs BEFORE enqueuing, and
    # a $0 24h cache hit is exempt from all of them (it must always return its id
    # so the email gate can post against the submission). The IP hash reuses the
    # existing ``ip_hash_salt`` above — there is deliberately no second salt.
    #
    # Master kill-switch. Default OFF: while False a FRESH submit is parked with
    # a friendly 503 and records nothing; the operator flips it True at P5.11
    # go-live, so the public surface stays dark in every environment until then.
    checker_enabled: bool = False
    # Per-IP: max checker submissions from one ip_hash per rolling hour; over
    # this a fresh submit gets 429 + Retry-After. 0 is a kill-switch (rejects
    # every fresh submit), the same 0-semantics as the analyses limits above.
    checker_rate_limit_per_ip_hour: int = 10
    # Per-brand: max FRESH runs (new kind='checker' rows) of one normalized
    # (brand, category, lang) per rolling day; over this a fresh submit gets 429.
    # Bounds a single hot brand hammered from many IPs. A cache-served repeat is
    # not a fresh run and never counts. 0 = kill-switch.
    checker_rate_limit_per_brand_day: int = 20
    # Daily USD cap on summed checker responses.cost_usd (rolling 24h, matching
    # the analyses daily-cap window). At/over the cap a fresh run is refused with
    # a friendly at-capacity 503; a cache hit still returns. Under DRY_RUN every
    # cost is 0, so any positive cap never trips.
    checker_daily_usd_cap: float = 5.0

    # Transactional email via the Resend REST API (P5.13). Fail-open + env-gated:
    # send_email is a NO-OP unless emails_enabled is True AND resend_api_key is
    # non-empty, and it never raises (see ADR-25). Default OFF so no environment
    # sends mail until the operator opts in. email_from must be a Resend-verified
    # domain before real recipients receive anything — the default onboarding@
    # resend.dev only delivers to the Resend account owner (testing mode).
    emails_enabled: bool = False
    resend_api_key: str = ""
    notify_email: str = ""
    email_from: str = "onboarding@resend.dev"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (read once per process)."""
    return Settings()
