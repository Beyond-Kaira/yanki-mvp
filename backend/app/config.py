"""Application settings, loaded from environment variables (12-factor style).

Every value has a safe default so the app boots with zero configuration. The most
important default is ``dry_run=True``: out of the box the pipeline runs on the
deterministic mock provider and spends $0.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
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

    # Authentication / JWT
    #
    # The signing key is intentionally blank by default. Token creation and
    # validation will fail closed until a real key is supplied through the
    # environment. SecretStr prevents accidental disclosure in logs/repr output.
    jwt_secret_key: SecretStr = SecretStr("")
    jwt_issuer: str = "yanki-api"
    jwt_audience: str = "yanki-web"
    jwt_access_token_minutes: int = Field(default=15, gt=0)
    jwt_refresh_token_days: int = Field(default=30, gt=0)
    jwt_clock_skew_seconds: int = Field(default=30, ge=0)

    # Production refresh cookies are Secure by default. Local development can
    # explicitly override this to false because localhost normally uses HTTP.
    auth_refresh_cookie_name: str = "yanki_refresh_token"
    auth_refresh_cookie_secure: bool = True

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
    # Dollars per Tavily search, counted into responses.cost_usd. Tavily bills in
    # plan-dependent API credits that no code here can read, so this is a pinned
    # estimate deliberately set high — an over-estimate makes a cost cap fail
    # safe. Correct it in deploy/.env once a real invoice exists (tech-debt #58).
    tavily_search_usd: float = 0.008

    # Backlink Intelligence (Phase 8 / M2). OFF by default and dark until the
    # operator picks a vendor and a budget (operator item A4) — the module runs
    # end-to-end on the deterministic mock meanwhile, at $0. Same kill-switch
    # shape as CHECKER_ENABLED / SERP_ENABLED.
    backlinks_enabled: bool = False
    backlink_vendor: str = "mock"

    # Pipeline behaviour
    dry_run: bool = True
    prompt_count: int = 10
    panel_engines: str = "anthropic,openai,gemini,perplexity"
    max_responses_per_job: int = 60

    # Worker / queue
    worker_poll_seconds: int = 2
    stale_claim_seconds: int = 300

    # Worker liveness (ADR-47). The worker owns no HTTP surface, so it proves it
    # is alive by touching a file on a volume the api also mounts — the cheapest
    # thing that works, since a heartbeat table would need a migration and a
    # heartbeat endpoint would mean giving the worker a web server. `/healthz`
    # reports its age and the compose healthcheck reads the same file.
    #
    # The beat is written on every poll AND at the start of every pipeline step,
    # so an idle worker beats every WORKER_POLL_SECONDS (2s) and a busy one beats
    # at each step boundary. The stale window has to exceed the longest single
    # *step*, which is `execute` — up to MAX_RESPONSES_PER_JOB paid calls — so it
    # is set well above it. Erring long is the cheap direction: this signal must
    # mean "stopped", and a window that flags a slow-but-working job is a signal
    # people learn to ignore.
    worker_heartbeat_path: str = "/var/run/yanki/worker.heartbeat"
    worker_heartbeat_stale_seconds: int = 1800

    # Site Audit enqueue kill-switch (S24). OFF by default, same shape as
    # backlinks_enabled above. Production runs exactly db/api/worker/searxng/web
    # and NONE of them drains the site-audit queue — the GEO worker consumes the
    # analyses queue, not this one — so a queued crawl sits `queued` forever. While
    # False, the two routes that queue a crawl are refused 404 the same way the
    # backlink module goes dark; reads of existing projects and audits stay open,
    # so nobody loses access to data they already have. The operator flips this
    # True only once a Chromium audit worker ships with egress and settings
    # isolation (M3) — see docs/site-audit-integration.md.
    site_audit_enabled: bool = False

    # Site Audit runs in a separate worker and queue. Browser crawls heartbeat
    # after every persisted page, so a longer stale window tolerates one slow
    # navigation without letting a crashed job remain running forever.
    site_audit_worker_poll_seconds: int = Field(default=2, gt=0)
    site_audit_stale_claim_seconds: int = Field(default=900, gt=0)
    site_audit_page_timeout_ms: int = Field(default=30_000, ge=1_000)
    site_audit_render_wait_ms: int = Field(default=1_500, ge=0)
    site_audit_crawl_delay_seconds: float = Field(default=0.25, ge=0)
    site_audit_max_robots_bytes: int = Field(default=512_000, ge=1_024)
    site_audit_sitemap_url_limit: int = Field(default=1_000, ge=0, le=10_000)
    site_audit_max_sitemap_bytes: int = Field(default=5_000_000, ge=1_024)
    site_audit_max_html_chars: int = Field(default=2_000_000, ge=10_000)
    site_audit_max_queue_urls: int = Field(default=5_000, ge=10, le=50_000)

    # A navigation that times out is NOT a navigation that stopped: `page.goto`
    # raising leaves Chromium still fetching that URL, so a slow target grew a
    # backlog of inflight loads which then interrupted each other — one slow
    # page became a chain of failures, and the crawl kept adding load to a site
    # that had already stopped answering. The crawler now drops the page after
    # every failed navigation; these two bound what it does next.
    #
    # The backoff cap is how far the politeness delay may grow while failures
    # are consecutive. Re-asking at full speed is the worst possible answer to
    # "the target is not responding", because it feeds whatever is throttling.
    # The floor is always the robots.txt/politeness delay, never below it.
    #
    # The consecutive-failure stop ends the crawl outright: once N navigations
    # in a row have failed, the rest of the page budget buys nothing but
    # timeouts. Measured 2026-08-17 against a real target: 82 of 100 pages
    # failed, 64 of them in one unbroken run, costing ~41 minutes and leaving a
    # health score computed from the 18 pages that survived. 0 disables the stop.
    site_audit_failure_backoff_max_seconds: float = Field(default=10.0, ge=0)
    site_audit_max_consecutive_failures: int = Field(default=10, ge=0)

    # Plan quota enforcement (P7.6). ON by default: a plan tier that nothing
    # enforces is decorative, which is what this flag exists to stop being true.
    #
    # It is a kill switch, not a feature gate — the difference matters. The
    # other flags in this file (checker/backlinks/site_audit) default OFF and
    # hide unfinished work; this one defaults ON and exists so the operator can
    # turn enforcement OFF from `deploy/.env` without a code change, on a box
    # that auto-deploys on merge and has no staging. Off means the quota is
    # counted nowhere and never refuses; every other guard (per-IP rate limits,
    # the checker's daily USD cap, RBAC) is untouched by it.
    quota_enforcement_enabled: bool = True

    # Rate limiting (P5.0) — POST /api/v1/analyses now requires authentication
    # (ADR-45), but these stay as defence in depth: they bound one credential's
    # burst before a row is created or money is spent, which a monthly plan
    # quota does not.
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

    # SERP visibility (ADR-28) — read an OPEN-SOURCE metasearch instance
    # (SearXNG) to see whether the company also shows up in ordinary search
    # results, alongside the AI-answer GEO score. No vendor, no per-query bill:
    # the operator runs the instance.
    #
    # Default OFF, like checker_enabled and emails_enabled, because unlike the
    # LLM panel this needs a piece of infrastructure no environment has until
    # somebody stands it up. Under DRY_RUN an enabled run uses the deterministic
    # mock source instead, so CI exercises the whole path with no instance and
    # no outbound packet.
    serp_enabled: bool = False
    # Base URL of the SearXNG instance, e.g. http://searxng:8080 on the compose
    # network. The instance must have the JSON format enabled — it is off by
    # default (search.formats: [html, json] in its settings.yml).
    serp_base_url: str = ""
    # Queries per analysis. Each is one HTTP call to the operator's own
    # instance, so this is a politeness/latency budget rather than a cost cap.
    serp_query_count: int = 6
    serp_timeout_seconds: float = 10.0
    # Pinned rather than left to the instance: a metasearch instance geolocates
    # by its own egress IP, so an unpinned language makes two deployments'
    # numbers quietly incomparable.
    serp_language: str = "en"
    serp_categories: str = "general"
    # Optional comma-separated engine allowlist passed straight through; empty
    # means "whatever the instance has enabled".
    serp_engines: str = ""
    serp_safesearch: int = 0
    serp_max_results: int = 20

    # Keyword research preview (docs/keyword-preview-oss.md) — expand seeds via
    # the same SearXNG instance as SERP visibility. Default OFF until the
    # operator opts in. Under DRY_RUN an enabled run uses MockKeywordSource so
    # CI needs no instance; live/default product path is SearXNG.
    keyword_enabled: bool = False
    # Cap on ideas returned from one expand call (politeness / payload size).
    keyword_max_ideas: int = 50
    # Cap on local template filler rows (source=variant). 0 disables templates.
    keyword_variant_max: int = 3
    # Max SERP lookups per rank-check request (politeness budget).
    keyword_rank_max_queries: int = 10
    # Google Ads Keyword Planning metrics (volume/CPC). Default OFF until the
    # operator has developer token + OAuth + customer ids configured.
    keyword_ads_enabled: bool = False
    google_ads_developer_token: str = ""
    google_ads_client_id: str = ""
    google_ads_client_secret: str = ""
    google_ads_refresh_token: str = ""
    # Client account that owns the Keyword Planning lookup (digits; no dashes).
    google_ads_customer_id: str = ""
    # Manager (MCC) account id when calling as a manager (digits; no dashes).
    google_ads_login_customer_id: str = ""

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

    # Where this deployment is reachable from a browser. Used to build the links
    # that go INTO emails — an invitation link in particular — because a link is
    # the one thing the API cannot infer from the request that carries it: the
    # request arrives at the internal container, not at the public origin.
    #
    # Trailing slashes are stripped at use. The default matches the dev stack's
    # web port so `make dev` produces links that actually open.
    public_base_url: str = "http://localhost:8140"

    # How long an invitation link stays usable, in days. Long enough to survive a
    # holiday, short enough that a forgotten invitation is not a permanent
    # standing grant sitting in an inbox.
    invitation_ttl_days: int = Field(default=14, ge=1, le=90)


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (read once per process)."""
    return Settings()
