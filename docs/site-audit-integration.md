# Site Audit integration

Site Audit is a sibling product surface to AI Visibility, not a seventh GEO
pipeline step. It has its own authenticated projects, durable queue, worker, and
page results. Existing GEO/KYC pipeline files and the `analyses` queue are not
part of this feature.

## Product and persistence flow

> **The crawl is gated off by default (`SITE_AUDIT_ENABLED`).** No deployed
> service drains the site-audit queue — production runs `db/api/worker/searxng/web`,
> and `worker` consumes the GEO `analyses` queue, not this one — so an enqueued
> audit would sit `queued` forever. The gate falls on the *crawl*, not the SEO
> project, because that project is the shared entity Backlinks also hangs off
> (`/seo-projects/{id}/backlinks`); gating project creation on this flag would
> silently take Backlinks down with it. So while the flag is off: `POST
> /api/v1/seo-projects` **still creates the project** (and its tenancy mirror)
> but queues **no** first audit — its `latest_audit` comes back `null`; and
> `POST /api/v1/seo-projects/{id}/audits`, whose only job is to start a fresh
> crawl, is refused **404**, the same way the backlink module goes dark. The
> reads below stay open, so existing projects and audits remain viewable. Steps
> 2–3 describe the flow that runs only once the operator flips the flag on
> **and** an audit worker is deployed.

1. An authenticated user creates an SEO project for one root domain.
2. Project creation queues the first Site Audit (only while `SITE_AUDIT_ENABLED`
   is on; otherwise the project is created without an audit — see the note above).
3. The dedicated audit worker crawls the site and persists each completed page.
4. A project may have repeated audit runs, but only one queued or running audit.
5. Project and audit reads are always scoped to the authenticated user.

The feature owns `seo_projects`, `site_audits`, and `site_audit_pages`. Findings
use stable `code`, `severity`, `message`, and structured `details` fields, so
display text and per-page counts do not split one finding into unrelated groups.

## Implemented crawl behavior

- Crawl URLs are limited to HTTP and HTTPS on the normalized project domain.
- Default ports may move between HTTP and HTTPS; custom ports stay isolated.
- Binary/document extensions, fragments, tracking parameters, excessive query
  variants, sitemap count, queue size, and audited page count are bounded.
- `robots.txt` and same-origin sitemaps are read with streaming decoded-byte
  limits. Redirected final origins get their own cached robots policy check.
- Browser requests are checked against the shared public-host guard. DNS
  resolution failures are rejected, and non-HTTP(S) browser requests are
  aborted.
- Raw and rendered HTML are truncated before analysis/persistence. This is not
  yet a browser transfer limit; see the unresolved boundaries below.
- Schema checks only recognize Schema.org types and property names from the
  bundled ontology. They do not validate value types, required/recommended
  fields, JSON-LD semantics, or search-engine rich-result eligibility.
- Pages blocked by robots are recorded as notices and excluded from health
  scoring. An audit with no scoreable page has a null health score.

## Security boundary

The application-level public-host check and redirect checks are defence in
depth, not complete DNS-rebinding protection: Python and Chromium can resolve a
hostname at different times. Production still requires an approved egress
design that resolves and pins destinations while rejecting private, loopback,
link-local, and metadata networks.

Settings isolation for the audit worker is a *design goal, not a boundary that
exists.* `backend/app/site_audit/worker.py` calls the shared `get_settings()`
and holds the **entire** `Settings` object — the same one carrying `jwt_secret_key`,
every provider API key, and the Resend key. It does **not** receive only its
database URL and `SITE_AUDIT_*` values; a worker that crawls arbitrary
third-party pages would today have the full secret set in process memory. The
intended split — the audit worker receiving only its database URL and explicit
`SITE_AUDIT_*` settings, in an `audit-runtime` image target isolated from the
general deployment `.env` — is **not built**: `backend/Dockerfile` is a single
stage and installs no browser, so both the settings isolation and the Chromium
isolation described here are design, not reality. Tracked as backlog item
`site-audit-chromium-image-missing`. Nothing runs the audit worker in production
today, so no unisolated Chromium is executing — but this is also why the enqueue
route is gated off (`SITE_AUDIT_ENABLED`, see above): turning it on without that
isolation would strand audits *and*, once a worker existed, hand a page-crawling
container every secret in the deployment.

## Unresolved production decisions

The following are deliberately not claimed as implemented:

- filtered `audit-egress` proxy and network isolation;
- non-root Chromium with sandbox-compatible seccomp and container hardening;
- browser-level transfer, request, subresource, and total audit budgets;
- transient retry backoff and user-level audit quotas;
- an explicit migration-readiness gate for workers;
- real image build, browser smoke test, and production deployment verification.

These items must be resolved before treating the crawler as safe for untrusted
production targets.
