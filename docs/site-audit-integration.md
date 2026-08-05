# Site Audit integration

Site Audit is a sibling product surface to AI Visibility, not a seventh GEO
pipeline step. It has its own authenticated projects, durable queue, worker, and
page results. Existing GEO/KYC pipeline files and the `analyses` queue are not
part of this feature.

## Product and persistence flow

1. An authenticated user creates an SEO project for one root domain.
2. Project creation queues the first Site Audit.
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

The audit worker receives only its database URL and explicit `SITE_AUDIT_*`
settings. It does not inherit the general deployment `.env` containing auth or
provider secrets. Chromium is *intended* to be isolated to an `audit-runtime` image target —
**which is not built.** `backend/Dockerfile` is a single stage and installs no
browser, so today the isolation described here is a design, not a boundary that
exists. Tracked as backlog item `site-audit-chromium-image-missing`; nothing
runs the audit worker in production either, so no unisolated Chromium is
actually executing.

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
