# Yanki — Target Platform Architecture (planning)

*Audience: engineers planning M1+ work. This is the **architecture planning**
document for the platform roadmap ([roadmap.md](roadmap.md)) — where the
system is heading. It deliberately does not describe the running system:
[architecture.md](architecture.md) documents **as-built** and stays accurate
to code. Nothing here is implemented until an implementation-plan card says
so. Source models: the planning baseline
([Yanki_Geo_Intelligence_Report.pdf](Yanki_Geo_Intelligence_Report.pdf)
§7.13, §10) adapted to what the repo actually contains on 2026-08-05.*

**Status: adopted planning baseline — 2026-08-05 (session 20, ADR-33).**

---

## 1. Principles (carried over, not invented)

The MVP's architectural bets have held and stay: **sync Python + FastAPI**,
**Postgres as the source of truth AND the job queue** (`FOR UPDATE SKIP
LOCKED`) until measured pain says otherwise, **one image for api + worker**,
**generated OpenAPI contract** as the FE/BE seam, **DRY_RUN-first**
determinism ($0 CI), **boring technology, replaceable parts**. The platform
additions below extend these patterns rather than replacing them — every new
data dependency gets the same *protocol + adapters + mock + registry* seam
the code already uses three times (LLM `Provider`, `SerpSource`, site-audit
engine).

## 2. Tenancy & data layer (M1)

- Hierarchy: **Organization** (billing/security boundary) → **Workspace**
  (client/brand; branding + membership) → **Project** (tracked business:
  domain, locale, panels, competitor set) → module data (analyses, audits,
  backlinks, records). Personal org auto-created per signup; convert/join
  paths per baseline §10.4.
- `org_id` on every tenant-owned row; scoping enforced in the data-access
  layer (query helpers that *require* an org context), with Postgres RLS
  policies as defense-in-depth once the access layer is proven — not
  UI-level hiding, ever.
- Existing tables (`analyses`, `seo_projects`, `checker_submissions`,
  `geo_records`, …) gain org/workspace/project FKs via additive backfill
  migrations; ADR-30's migrate-before-serve discipline already covers the
  deploy path.
- `region` recorded on org from day one (M8 residency without a migration).

## 3. AuthZ: RBAC at the API layer (M1)

One permission service: `can(actor, resource:action, scope)` — role
capability ∩ workspace grant, deny-by-default (baseline §11). FastAPI
dependencies wrap every route; the UI only reflects. Client roles
(Viewer/Guest) are structurally isolated: their tokens cannot query
internal-lane or billing resources at the data layer. Platform roles
(Super Admin / Support) live above org scoping with mandatory audit +
logged impersonation. API keys and MCP sessions flow through the same
`can()` path — one enforcement seam for humans, keys, and agents.

## 4. Audit & event spine (M1, consumed by everything)

A single **event bus abstraction** (in-process + Postgres outbox now; a
broker only if volume demands): every mutating service emits domain events.
Three consumers from the baseline's "one truth, three consumers" rule:
**audit log** (append-only, before/after diffs, secret-redacted),
**usage metering** (credit ledger, quota counters, per-request provider
cost tags — extending today's `cost_usd`), and **notifications/analytics**
(M4 alerts, product funnels). Alert rules, playbook triggers (M7), and
webhooks all subscribe to the same events — built once.

## 5. Modules, not a monolith rewrite

Product surfaces are **modules** with a common shape: models (org-scoped) +
service + routes + UI + report blocks + quota class + feature flag.
Existing surfaces retrofit into the shape (GEO analyses, SERP visibility,
SEO audit, Site Audit); new ones (Backlinks M2, Keywords/Rank M6, Reviews
M5) are born in it. A module registers: its nav entry, its report sections
(M6 builder), its alertable events (M4), its API resources (M7), and its
credit meters (M1). The kill-switch pattern (`CHECKER_ENABLED`) generalizes
to per-module feature flags managed in the admin panel.

## 6. Data-provider seams (external dependencies)

| Seam | Exists today | Platform additions |
|---|---|---|
| `Provider` (LLM) | Anthropic, OpenAI, Gemini, Perplexity, OpenRouter, mock | per-org/per-key spend caps; provider health in admin; model/price pinning surfaced |
| `SerpSource` | SearXNG, mock | localized retrieval (gl/hl, coordinates) via a licensed SERP vendor adapter (M4-local/M6); multi-vendor failover |
| Search/grounding | Tavily (measured path) | cost tagging into ledger; fallback vendor |
| `BacklinkSource` | — | M2: licensed index adapters (DataForSEO-class first) + mock + liveness verifier |
| `KeywordSource` | — | M6: licensed keyword data adapter + mock |
| Integrations | Resend (email) | GBP OAuth (M5), GSC/GA4 read (M3/M6), Slack (M4), Stripe (M1), Zapier/Looker (M7) |

Every adapter call is **cost-tagged at the callsite** so gross margin per
org is observable in the admin usage page — the baseline's operational
requirement, and the discipline `cost_usd` already started.

## 7. Jobs & scheduling (M3/M4)

Postgres-as-queue stays; it gains: **job kinds with worker pools**
(analysis, site-audit — exists as a second queue already — scan refresh,
backlink refresh, report render), **priority classes** (interactive >
scheduled), **per-org fairness caps**, and a **scheduler** (a small
tick-worker materializing due schedules into jobs — quiet hours, timezone
aware). Escalation path if pin volume demands it (time-series to
partitioned tables → columnar store) is deferred until measured; schema
keeps `occurred_at`-partitionable shapes from M4.

## 8. Time-series & history (M4 foundation)

New append-only measurement tables (scores, ranks, presence, link deltas)
separate from operational rows: monthly-partitioned Postgres first;
aggregates retained indefinitely, raw detail per plan retention (24 months
paid — baseline §7.7). Dashboards read replicas/caches only when measured
load says so.

## 9. Reporting & render isolation (M6)

Report rendering (PDF/heavy HTML) runs as an isolated render job (the
site-audit worker pattern: separate image target, no app secrets) writing
artifacts to object storage with revocable share links. Never inside the
request path.

## 10. Deploy topology evolution

Today: one shared VPS, host nginx, compose project, auto-deploy-on-merge,
co-tenant discipline (never disturb the other sites). This carries M1–M3
if the site-audit/scan workers stay resource-capped (the SearXNG playbook:
pinned image, mem/cpu caps, no published ports). The known forcing
functions for a second box / managed Postgres: Chromium crawler load (M3),
scan cadence volume (M4+), and report rendering (M6). Decision deferred to
measured pressure; the compose-profile pattern keeps each addition opt-in.
Feature flags + audit (M1) are what make auto-deploy-on-merge safe as the
team grows — that is an explicit architectural dependency, not a nice-to-
have.

## 11. Security posture additions

M1: MFA, session/device management (family revocation exists), API-key
hashing + scoping, quota/spend caps per org, audit trail, secret-redaction
in diffs. M3: crawler egress isolation (the unresolved list in
[site-audit-integration.md](site-audit-integration.md) becomes the card
set). M7: agent write actions human-approval-gated by default, per-key
caps + kill switches. M8: SSO/SCIM, residency, SOC 2 evidence collection
riding the audit spine. OWASP ASVS L2 stays the bar (baseline §7.11).

## 12. What is explicitly deferred

Microservices, brokers, Kubernetes, multi-region, columnar stores, owned
crawl/keyword/backlink indexes, custom RBAC roles, and a mobile app — all
deferred behind measured need or milestone gates (M8/M9). The architecture
grows by adding seams to a modular monolith, which is what the codebase
already is.
