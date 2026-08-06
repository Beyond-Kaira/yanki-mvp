"""Application settings, loaded from environment variables (12-factor style).

Every value has a safe default so the app boots with zero configuration. The most
important default is ``dry_run=True``: out of the box the pipeline runs on the
deterministic mock provider and spends $0.
"""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# What Yanki asks Google for. A constant and not a setting, deliberately: a
# scope list is the blast radius of a stolen refresh token, and an environment
# variable is a place it can be widened without anyone reviewing the diff.
#
# ``openid`` + ``email`` are not conveniences. They make Google return an ID
# token, whose verified ``sub`` and ``email`` claims are the only trustworthy
# source of *which* Google account authorized a connection — the alternative is
# believing a value the caller supplied. ``webmasters.readonly`` is the narrowest
# Search Console scope: it can read properties and performance data and cannot
# submit, delete or change anything.
GOOGLE_OAUTH_SCOPES: tuple[str, ...] = (
    "openid",
    "email",
    "https://www.googleapis.com/auth/webmasters.readonly",
)


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

    # Google Search Console (Phase 9 / M3). OFF by default and dark until the
    # operator registers an OAuth client, the same kill-switch shape as
    # BACKLINKS_ENABLED. Nothing calls Google yet: this slice is the schema and
    # configuration foundation the OAuth routes will later read.
    gsc_enabled: bool = False
    google_oauth_client_id: str = ""
    # SecretStr for the same reason as jwt_secret_key: it keeps the value out of
    # logs, tracebacks and repr output.
    google_oauth_client_secret: SecretStr = SecretStr("")
    # Where Google returns the browser after consent. Configured rather than
    # derived from public_base_url, because that is the *web* origin and Google
    # comes back to the *api* — and because Google matches this string byte for
    # byte against the value registered in Cloud Console, so a value this code
    # assembled would be a value nobody registered. Blank here on purpose: the
    # dev value lives in deploy/.env.example, production's only in deploy/.env.
    google_oauth_redirect_uri: str = ""
    # URL-safe base64 32-byte Fernet key, used to encrypt stored Google refresh
    # tokens at rest. Deliberately NOT jwt_secret_key: signing and encryption
    # have different blast radii, and reusing one key would mean rotating the
    # JWT secret silently destroys every stored Google connection.
    token_encryption_key: SecretStr = SecretStr("")
    # How long one authorization attempt stays claimable. Long enough for a user
    # to pick an account and read a consent screen, short enough that an
    # abandoned attempt is not a standing grant.
    gsc_oauth_state_ttl_seconds: int = Field(default=600, gt=0)

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

    @field_validator("google_oauth_redirect_uri")
    @classmethod
    def _redirect_uri_is_absolute(cls, value: str) -> str:
        """Blank is allowed; anything else must be a URL Google will accept.

        Checked whenever a value is present, not only when GSC is enabled, so a
        typo is caught at boot rather than at the first click. Google rejects a
        redirect URI carrying a fragment outright, which is worth catching here
        instead of as an opaque error on its consent screen.
        """

        value = value.strip()
        if not value:
            return value

        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.netloc or parts.fragment:
            raise ValueError(
                "GOOGLE_OAUTH_REDIRECT_URI must be an absolute http(s) URL without a fragment"
            )
        return value

    @model_validator(mode="after")
    def _google_config_is_complete_when_enabled(self) -> Settings:
        """Turning GSC on without its credentials fails the boot, not the click.

        The alternative — defaulting to a friendly 503 at use time, the shape
        ``jwt_secret_key`` uses — hides an operator mistake behind a symptom a
        user reports. GSC_ENABLED is an explicit opt-in, so an incomplete one is
        a deploy that should be refused: on this repo's auto-deploy the container
        fails its health check and rolls back, which is the loudest safe outcome.

        Only names are reported. No value from this model reaches the message.
        """

        if not self.gsc_enabled:
            return self

        required = (
            ("GOOGLE_OAUTH_CLIENT_ID", self.google_oauth_client_id),
            ("GOOGLE_OAUTH_CLIENT_SECRET", self.google_oauth_client_secret.get_secret_value()),
            ("GOOGLE_OAUTH_REDIRECT_URI", self.google_oauth_redirect_uri),
            ("TOKEN_ENCRYPTION_KEY", self.token_encryption_key.get_secret_value()),
        )
        missing = [name for name, value in required if not value.strip()]
        if missing:
            raise ValueError(
                "GSC_ENABLED is on but these are not configured: " + ", ".join(missing)
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (read once per process)."""
    return Settings()
