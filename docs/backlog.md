# Yanki — Engineering Backlog

*Audience: engineering lead + implementing agents. This is the **prioritized queue**: the ordered, deduplicated, dependency-resolved list of what to build next. It was generated on `2026-08-05` by merging five parallel backlog surveys (admin-panel completion, tech-debt, infrastructure, feature-parity, quality/security) against the live codebase, then dropping duplicates and anything already shipped.*

*How it relates to the other planning docs: [roadmap.md](roadmap.md) is the **what/why/when** (milestones M1–M9); [implementation-plan.md](implementation-plan.md) is the **card ledger** (Phase 0–15, the authoritative per-card status); this file is the **queue** that sits between them — it takes the roadmap's milestones and the ledger's open cards and orders them by risk and dependency. Where the ledger and this file disagree on status, the ledger wins. Every item keeps its survey `id` so a PR can cite it.*

*State at generation time (session 22, per implementation-plan §Phase 7): M1 stages **A1–A4 are done** (tenancy backfill, RBAC enforcement, audit spine, Admin Panel v1). **A5–A9 are open** — that is the bulk of P1 below. M2 backlink engine is built in code (P8.1/P8.5/P8.6/P8.7 done) but has no router and no customer surface. Everything M3+ is unstarted.*

*Delta since generation (session 23): **P8.3 shipped whole** — the backlink router, and then the screens. "No router and no customer surface" above is stale on both counts. What is still missing is a licensed index, not code; see P2 below.*

*Delta since generation (session 24): four P0 items closed — `cap-container-resources`, `bound-container-logs`, `fix-preflight-key-check`, `harden-rollback-pruned-image`, `ci-validate-prod-compose` — plus the interim Site Audit enqueue gate. `session-device-management` and `org-switcher-ui-multi-org-me` shipped from P1.*

*Delta since generation (session 26), second loop: **`analysis-history-per-org` shipped** (ADR-49) — the screen that makes session 25's `org_id` attribution visible to the customer, and the first application call site of the fail-closed `tenancy.scoped()` seam that three documents had described as shipped with zero callers.*

*Delta since generation (session 26): **`audit-coverage-public-writes` shipped** (ADR-48) — six mutating paths emitted nothing, and the sharp one was refresh-token reuse detection, which revokes an entire sign-in family for suspected theft and wrote no record at all. Also added `billing:quota_denied`, which is not a mutation: session 25 made every organization Free by default, so a refusal is now the likeliest thing to happen to a live user and "my analysis just fails, why?" had an answer in no log and no screen. This closes the last of A9's missing-emitter backlog; what remains for the exit gate is `cross-tenant-leakage-suite` and the deliberate `audit-emit-no-outbox` trade. **Before that, two CI gates that were red on session 25's branch were fixed** — the scoped formatting gate, and the SERP stack check, which runs a whole analysis through compose and had been 401ing since ADR-45 closed `POST /analyses` to anonymous callers. Neither was visible from a laptop; both were found by pushing the branch.*

*Delta since generation (session 25): **`enforce-quota-on-spend-paths` shipped** (ADR-45), which unblocks `stripe-subscription-lifecycle`, `system-admin-pages` and `cross-tenant-leakage-suite` on the code side — every one of them listed it as a dependency. It also closed a hole nobody had filed: `POST /api/v1/analyses` took no authentication, so every customer's analysis belonged to no tenant. Two new rows appear in P1 below (`grant-monthly-plan-credit`, `analysis-history-per-org`), both created by that change rather than found by a survey. **Second loop: `database-backups` and `pre-migration-snapshot`** (ADR-46) — this file listed both as `infra`, unowned, and the operator file listed the first as wholly the operator's. Most of it was neither: the dump, the verification, the rehearsed restore and the deploy-time gate are engineering and are now built and exercised against live production. What genuinely needed the operator turned out to be two lines (an off-box destination and a cron entry). **Third loop: `worker-liveness-healthcheck` and `deep-health-endpoint`** (ADR-47) — one defect wearing two hats, *the system reports health it has not checked*: `/healthz` was a hardcoded literal that the deploy gate greps, so a release with an unreachable database was recorded as last-good, and a `while True` worker that stopped looping left the container `running` and the queue quietly undrained. **That empties the P0 band apart from `format-backlog-repo-wide`, which should stay parked.***

## How to read this

- **Priority bands** answer "when." **P0** = a live production risk on the shared VPS, or a thing that blocks M1 from proceeding cleanly. **P1** = M1 (the next milestone, Phase 7 A5–A9). **P2** = M2 (the milestone after, Backlink Intelligence). **P3** = M3–M7 and opportunistic work.
- **`track`** answers "which lane." `feat` = customer-visible capability; `infra` = platform/operational/security work. The **Infrastructure track** section re-collects every `infra` item thematically so that lane can be read on its own.
- **`depends-on`** lists *kept* item ids or, in *italics*, an **external** blocker (an operator decision, a vendor, or a legal document) — those are enumerated in the External dependencies section.
- Milestone tags map to roadmap milestones; `—` means the work has no milestone home and rides independently (operator-gated or pure hygiene).
- Sizes are S/M/L as the surveys estimated them, carried through merges by taking the larger where two items combined.

---

## Priority 0 — blocking or at risk

These are not milestone features. They are standing risks on a box that is *the production VPS, shared with four other live tenants, on a chronically tight disk, that auto-deploys on merge* (per MEMORY). Each is one event away from an incident, or it silently defeats a safety mechanism we believe is protecting us. Do these first; most are S/M and several are independent single-PR fixes.

| id | title | track | size | depends-on |
|---|---|---|---|---|
| `database-backups` | ~~Scheduled Postgres backups, off-box copy, tested restore runbook~~ (**engineering half done, session 25** — ADR-46: `deploy/backup.sh` with a full read-back verification, `deploy/restore-check.sh`, and a rehearsed restore of live production. Residual is operator-only: an off-box destination and a cron line — tech-debt #79/#80) | infra | M | — |
| `pre-migration-snapshot` | ~~Snapshot before every remaining M1 live-DB migration (A5–A8), gate the deploy on it~~ (**done, session 25** — `deploy.sh` compares `alembic current` with `alembic heads`, dumps when they differ, and aborts the deploy if the dump fails. Unproven against a real migration: tech-debt #78) | infra | M | `database-backups` |
| `cap-container-resources` | ~~`mem_limit`/`cpus` on api/worker/web so one container can't starve the co-tenants~~ (**done, session 24** — ADR-41) | infra | M | — |
| `bound-container-logs` | ~~Cap json-file log size on db/api/worker/web~~ (**done, session 24** — ADR-41) | infra | S | — |
| `worker-liveness-healthcheck` | ~~Heartbeat healthcheck so a wedged `while True` worker is detected~~ (**done, session 25** — ADR-47: the worker beats to a shared volume, a compose healthcheck reads it, `/healthz` reports its age). **Not `restarted`** — Compose never restarts a container for being unhealthy, so that half is still open: tech-debt #81 | infra | M | — |
| `deep-health-endpoint` | ~~Make `/healthz` a real readiness probe — the deploy gate greps it~~ (**done, session 25** — ADR-47: database, schema, plan catalog, queue, worker and providers; only the database and an empty catalog under enforcement can fail it; component detail is withheld from the public edge) | infra | S | — |
| `fix-preflight-key-check` | ~~`check_env.py` must validate the keys the measured path actually needs~~ (**done, session 24** — ADR-42) | infra | S | — |
| `harden-rollback-pruned-image` | ~~Fix `rollback.sh`'s pruned-image branch so it can't resurrect the fused migrate-on-boot compose~~ (**done, session 24** — ADR-42) | infra | M | — |
| `ci-validate-prod-compose` | ~~Validate `docker-compose.prod.yml` + deploy driver in CI~~ (**done, session 24** — `scripts/check_prod_compose.py`, asserted against the *rendered* config) | infra | S | — |
| `format-backlog-repo-wide` | Repay the ~50-file `ruff format` backlog in one PR before Phase-7 lanes edit those files in parallel | infra | S | — |

**Why these and not the M1 features first.** `database-backups` + `pre-migration-snapshot`: the `yanki_pgdata` volume is the only copy of every analysis, user, session and — from M1 — every `audit_events` and billing row, and A5–A8 each add a live-DB migration on top. A backfill that mangles rows today is permanent; rollback restores the image, never the data. `cap-container-resources` + `bound-container-logs`: the analysis worker already fetches arbitrary third-party pages (discovery/SPA mining) unfenced, and only searxng has a log cap — an OOM or a traceback loop takes pulse-prod/brier/antmedia/evrak-app down with us, not just Yanki. `deep-health-endpoint` + `fix-preflight-key-check`: the deploy gate greps a hardcoded `{"status":"ok"}` and the preflight checks the wrong provider keys, so a broken deploy ships green — on auto-deploy-to-prod that is a live outage the gate exists to catch. `format-backlog-repo-wide` is here because it is the cheap unblock for parallel M1 lanes: the scoped formatter gate only holds touched files, so two Phase-7 lanes editing the same unformatted file produce unreadable reformat-vs-reformat conflicts.

**One latent UX void, mitigated here, fixed in M3.** The Site Audit UI is user-reachable (PR #24/#25) and its enqueue path is mounted, but **no worker drains it** — `deploy/docker-compose.prod.yml` runs exactly five services (`db`, `api`, `worker`, `searxng`, `web`) and none of them is the site-audit worker, so any audit a user starts would sit `queued` forever.

*Checked against production rather than assumed (2026-08-05): `seo_projects` and `site_audits` both hold **zero rows**, so nothing is stranded today and this is a trap that has not yet been sprung, not an incident in progress. It is P0 because the door is open and the cost of closing it is a config flag, not because anyone has walked through it.* The full fix (deploy the worker + Chromium image + crawler hardening) is M3 (`deploy-site-audit-worker` and its cluster in P3). The interim P0 action is the cheap half of that same item: **gate/hide the Site Audit enqueue in prod until the M3 cluster lands**, so users don't submit into a void and we don't expose an unhardened root-Chromium crawler. No separate card — this is the "or block audit enqueue until it runs" clause of `deploy-site-audit-worker`.

---

## Priority 1 — the next milestone (M1, Phase 7 A5–A9)

M1 is large and mostly open. A1–A4 shipped the tenancy spine, RBAC enforcement, the audit store, and the Admin Panel v1. P1 is everything the milestone still owes: auth completion, billing/quotas, the platform back office, the system pages, and the hardening exit gate. Per admin-panel-plan §9, A5–A8 parallelize across lanes once A2's enforcement seam exists (it does); A9 is the merge gate that runs last.

### Features (customer-visible / org-admin surface)

| id | title | size | depends-on |
|---|---|---|---|
| `enforce-quota-on-spend-paths` | ~~Wire `check_quota`/`consume_quota`/`reserve` into the analysis, checker, and **site-audit** submission paths~~ (**done, session 25** — ADR-45). Analyses, site audits and projects are metered; `POST /analyses` had to be closed to anonymous callers first, since a quota needs a tenant. The checker stays **capped, not metered** — it is anonymous by design and has no org to charge. Residual: the plans' `monthly_credit_usd` is never granted, so `reserve()`'s credit gate can still never pass | M | — |
| `stripe-subscription-lifecycle` | Subscription lifecycle + plan assignment (Stripe test mode) + billing-visibility API (invoices, credit ledger, spend-by-workspace) — no `Subscription` row is ever created today | L | `enforce-quota-on-spend-paths`, *Stripe account*, *terms text* |
| `password-reset-endpoint` | Enumeration-safe password-reset endpoint + restore the removed `/forgot-password` screen (repays #49) | M | — |
| `mfa-totp-and-org-policy` | TOTP MFA (enroll/verify/backup codes, admin reset) + org require-MFA policy (the audit spine already reserves the `mfa` event class) | L | — |
| `session-device-management` | Session/device list with remote revoke and sign-out-everywhere (family revocation exists — expose it) | M | — |
| `org-switcher-ui-multi-org-me` | Make `/auth/me` return all orgs + build the org switcher (contractor mode; the `X-Org-Id` seam already exists) | M | — |
| `account-lifecycle-gdpr-owner-transfer` | GDPR delete (soft window), explicit owner-transfer, artifact-transfer wizard for a departing user's schedules/keys/reports | M | — |
| `workspace-project-api-and-ui` | Workspace + project CRUD API and admin screens (schema exists, a default workspace is created at signup, but there is no surface to manage either) | M | — |
| `platform-back-office` | Super Admin/Support back office: cross-org directory, plan overrides, logged impersonation (roles/permissions defined, no platform-scoped route exists) | L | — |
| `org-api-keys` | Org-scoped API keys: issue/rotate/revoke with scopes, caps, last-used, hashed at rest (`apikey:issue` is granted but there is no table/route) | M | — |
| `audit-log-csv-export` | CSV export on the audit log, itself audit-logged (§6 requires it; list/filter/history/integrity exist, export does not) | S | — |
| `grant-monthly-plan-credit` | Grant each plan's `monthly_credit_usd` at the start of a billing period — until then every balance is 0, so `reserve()`'s credit gate would refuse every call and is therefore used only on the dark backlink path (added session 25) | S | `stripe-subscription-lifecycle` |
| `analysis-history-per-org` | ~~A list of the organization's analyses~~ (**done, session 26** — ADR-49. `GET /api/v1/analyses` + the `/analyses` screen + a nav entry. Signed-in and org-scoped, deliberately unlike the detail route it sits above: an id is a capability, a list is not. Also the **first application call site of `tenancy.scoped()`**. Residuals: tech-debt #87 (no index — it is a migration, gated on B13) and #88 (the list does not poll)) | M | — |

### Infrastructure (platform / audit integrity / security hardening for M1)

| id | title | size | depends-on |
|---|---|---|---|
| `feature-flags-system` | DB-backed feature flags (global + per-org) with audited flips, replacing the env-boolean kill-switches that need a redeploy | M | — |
| `system-admin-pages` | System visibility: jobs/queues board (retry/cancel/reaper), AI-provider status + per-provider spend, usage analytics, error surface (absorbs `queue-observability`) | L | `enforce-quota-on-spend-paths` |
| `observability-error-tracking` | Error tracking + log aggregation (request_id-linked) + a production alert path (Sentry/GlitchTip) — today only CI/Deploy failures page anyone | L | — |
| `auth-endpoint-rate-limiting` | Rate-limit login/signup/refresh/invitation-accept — public auth endpoints have no throttle, lockout, or backoff today | M | — |
| `audit-coverage-public-writes` | ~~Emit `audit_events` from the paths the spine skips: analyses, checker, waitlist, billing~~ (**done, session 26** — ADR-48. Six paths closed, including refresh-token reuse detection, which revoked a whole sign-in family for suspected theft and recorded nothing; plus `billing:quota_denied`, which is a *refusal* rather than a mutation and is audited because ADR-45 made refusals the likeliest thing to happen to a live user. The rule it settled on is **every mutation with a consequence emits, and every deliberate silence has a test asserting it** — a successful token rotation is a mutation and is silent on purpose. Residuals: tech-debt #84–#86) | M | — |
| `audit-emit-no-outbox` | Make `audit.emit` loss-evident (transactional outbox/retry) — it swallows every exception and returns `None`, so a DB hiccup silently drops a compliance event (absorbs `audit-write-loss-outbox`) | M | `cross-tenant-leakage-suite` |
| `cap-and-validate-email-columns` | Bound + validate the unauthenticated email columns (waitlist, checker lead) — unbounded `Text`, minimal regex, no signup cap | S | — |
| `pii-retention-and-erasure` | Define PII retention, erasure path, privacy docs — emails stored raw and copied into audit payloads with no retention window | M | `account-lifecycle-gdpr-owner-transfer` |
| `secrets-rotation-procedure` | Document + enable rotation for `deploy/.env` (JWT key, provider keys, DB password); M1 adds Stripe/MFA/api-key secrets to the same file | M | — |
| `refresh-test-suite-doc` | Update `test-suite.md` to cover the ~10 new backend suites (admin/audit/tenancy/invitations/permissions/billing/backlinks/site-audit) it omits | S | — |
| `cross-tenant-leakage-suite` | The A9 cross-tenant leakage / permission-fuzzing suite — the named M1 exit gate ("zero cross-tenant reads"), the merge gate for everything after (dedup of two survey entries) | M | `enforce-quota-on-spend-paths`, `platform-back-office` |

**Notes.** `feature-flags-system` and `system-admin-pages` are P7.7/P7.8 content; they are tagged `infra` because they exist as *operational* tooling for a two-developer auto-deploy shop, not as customer features. `cross-tenant-leakage-suite` must run against the finished P7.6/P7.7 surfaces, so it lands last in M1; `audit-emit-no-outbox` is the one A9 residual that is a deliberate trade (never 500 a request on an audit-write failure) rather than a bug, and it is hardened in the same A9 pass. `stripe-subscription-lifecycle` cannot *sell* a plan until the terms text (#50, legal) exists — see External dependencies.

---

## Priority 2 — the milestone after (M2, Backlink Intelligence)

The M2 engine is built, registered in `main.py`, and — since session 23 — has screens: P8.3 is done end to end and the nav entry is `live`. What now stands between it and a paying customer is **a licensed index**: `BACKLINKS_ENABLED` stays off in production because every number the mock produces is fixture data, and shipping fixture data as a customer's backlink profile is the one mistake this module cannot recover from. M2's remaining work is therefore the vendor adapter, not the product surface.

| id | title | track | size | depends-on |
|---|---|---|---|---|
| `backlink-inventory-ui-and-api` | ~~Backlink router + inventory / referring-domains / anchors UI with filter/sort~~ (**done, session 23** — P8.3). Residual only: XLSX beside the shipped CSV, and a competitor-management screen for the API that already exists | feat | S | — |
| `backlink-vendor-adapter-metered-import` | First licensed `BacklinkSource` adapter with cost-tagged, quota-gated import (P8.2) — only the mock adapter exists, so every number is fixture data | feat | M | `enforce-quota-on-spend-paths`, `stripe-subscription-lifecycle`, *backlink vendor A4* |
| `backlink-monitoring-scheduled-refresh-liveness` | Scheduled refresh + `LinkVerifier` liveness so new/lost/velocity events actually accrue (P8.4 residual) | feat | M | `backlink-vendor-adapter-metered-import`, *minimal scheduler seam* |

**Ordering honesty.** `backlink-inventory-ui-and-api` is done, built against the mock adapter as predicted. That makes `backlink-vendor-adapter-metered-import` the true gate on M2: everything else in the milestone now works and is simply not switched on. `backlink-monitoring-scheduled-refresh-liveness` needs a scheduler, and the full scheduler is an M4 item (`scheduled-recurring-runs-history`) that comes *after* M2 in the fixed order. The roadmap resolves this: M2 builds a **minimal scheduling seam** if M4 hasn't landed. Treat that seam — not the full M4 scheduler — as the dependency, and design it so M4 subsumes it.

---

## Priority 3 — later (M3, M4, M6, M7, and opportunistic)

Grouped by milestone. Sizes and dependencies are carried from the surveys; these are decomposed into cards only when their milestone starts (roadmap Phases 9+).

### M3 — Technical SEO & Site Audit productization

| id | title | track | size | depends-on |
|---|---|---|---|---|
| `deploy-site-audit-worker` | Add the dedicated site-audit worker to prod (and dev) compose so queued audits are processed (dedup of four survey entries) | infra | M | `cap-container-resources` |
| `site-audit-chromium-image-missing` | Build the `audit-runtime` image target with Chromium — `crawler.py` launches Chromium but the single-stage Dockerfile installs no browser | infra | M | `deploy-site-audit-worker` |
| `site-audit-egress-isolation` | Resolve crawler egress/SSRF isolation before pointing Chromium at untrusted targets from the shared VPS (rebinding/metadata-endpoint exposure) | infra | M | `deploy-site-audit-worker` |
| `site-audit-worker-env-isolation-unbuilt` | Actually isolate the audit worker's env from auth/provider secrets — the doc claims isolation, `worker.py` calls the full `get_settings()` | infra | M | `deploy-site-audit-worker` |
| `crawler-silent-html-swallow` | Stop the crawler persisting decode failures as empty pages (misreported as thin-content SEO findings) | infra | S | — |
| `audit-breadth-cwv-hreflang-llmstxt` | Broaden audit checks to parity: Core Web Vitals, redirect-chain/broken-link depth, hreflang, llms.txt; fix six-page findings reading as site-wide (#45/#48) | feat | M | `deploy-site-audit-worker` |
| `csv-xlsx-exports` | CSV/XLSX export on every data surface (findings, backlinks, results) — buyers treat no-export as lock-in | feat | M | — |

Two survey items — `site-audit-crawler-production-hardening` and `harden-site-audit-crawler` — were umbrella framings of this cluster and are dissolved into the granular rows above. `site-audit-no-quota` is folded into `enforce-quota-on-spend-paths` (that M1 item explicitly names the site-audit submission path as one of the three it must gate).

### M4 — AI Visibility & GEO Monitoring (the product becomes recurring)

| id | title | track | size | depends-on |
|---|---|---|---|---|
| `scheduled-recurring-runs-history` | Scheduler + time-series storage that turns one-shot analyses into tracked visibility — no scheduler and no time-series model exist today; blocks the whole retention thesis | infra | L | `enforce-quota-on-spend-paths` |
| `alert-engine-rules-channels-digest` | Alert engine: threshold/event rules, email/Slack/in-app, digest bundling, dedup, quiet hours (today only a single operator email fires on every run) | feat | L | `scheduled-recurring-runs-history` |
| `project-dashboards-and-weekly-digest` | Per-project/workspace dashboards (KPI tiles + trends) + weekly digest email (the signed-in dashboard is a bare URL box today) | feat | M | `scheduled-recurring-runs-history` |
| `local-geo-conditioned-visibility` | Location-conditioned AI-visibility sampling (AI-SoLV per location) — the planning baseline's hero bet, entirely unbuilt | feat | L | `scheduled-recurring-runs-history`, *local data vendor A5* |

### M6 — Reporting & agency wedge

| id | title | track | size | depends-on |
|---|---|---|---|---|
| `report-builder-pdf-live-link` | Modular report builder (PDF + revocable live links, scheduled, AI-drafted commentary) — the #1 retention artifact agencies resell | feat | L | `scheduled-recurring-runs-history` |
| `white-label-and-client-portal` | White-label (logo → theme → custom domain/from-address) + free client-viewer portal seats — decision criterion #1 for the agency ICP | feat | L | `report-builder-pdf-live-link` |

### M7 — Public API

| id | title | track | size | depends-on |
|---|---|---|---|---|
| `publish-api-reference-docs` | Consumer-facing, authored OpenAPI reference (not just the type-gen artifact); also disable the internal `/docs`,`/redoc`,`/openapi.json` on the prod origin | feat | M | `org-api-keys` |

*The internal-`/docs`-exposure half of this item is a cheap information-disclosure hardening — pull the toggle forward into the A9 hardening pass; the authored reference is genuine M7 work.*

### Opportunistic / operator-gated (no milestone home)

| id | title | track | size | depends-on |
|---|---|---|---|---|
| `public-checker-go-live` | Execute the P5.11 checker go-live: live four-engine smoke, cost soak, `CHECKER_ENABLED` flip, launch | feat | M | `tavily-price-unverified-live-cap`, *operator go/no-go* |
| `tavily-price-unverified-live-cap` | Verify `TAVILY_SEARCH_USD` against a real invoice before the checker daily cap goes live (the cap is now functional but denominated partly in a guessed price) | infra | S | *Tavily invoice* |
| `architecture-doc-stale-execute` | Finish the architecture.md/README sync away from the retired 4-engine panel (open half of #54) | infra | S | — |
| `ci-concurrency-and-paths` | Add `concurrency:` cancellation + path filters to CI to stop docs-only PRs building the full e2e stack | infra | S | — |

`public-checker-go-live` is fully built and deployed-but-dark; it is independent of M1+ and can ship any day the operator says so, once `tavily-price-unverified-live-cap` closes the cost-cap accuracy gap.

---

## Infrastructure track (cross-cutting)

The same `infra` items, re-collected so the platform/operational lane can be read on its own and staffed independently of the feature lanes. Ordered within each theme by urgency.

- **Operational safety (P0, live risk):** `database-backups` · `cap-container-resources` · `bound-container-logs` · `worker-liveness-healthcheck` · `deep-health-endpoint`. The shared-VPS survival set — data durability, resource fencing, and honest liveness.
- **Deploy-pipeline safety (P0/P1):** `fix-preflight-key-check` · `harden-rollback-pruned-image` · `ci-validate-prod-compose` · `pre-migration-snapshot` · `format-backlog-repo-wide` · `ci-concurrency-and-paths`. Everything that makes a merge-is-a-release pipeline trustworthy.
- **Audit integrity (P1, M1 A3/A9):** `audit-coverage-public-writes` · `audit-emit-no-outbox`. The append-only log is tamper-evident but not yet complete or loss-evident.
- **Security & data hardening (P1, M1):** `auth-endpoint-rate-limiting` · `cap-and-validate-email-columns` · `secrets-rotation-procedure` · `pii-retention-and-erasure`.
- **Observability & system surface (P1, M1 A7/A8):** `feature-flags-system` · `system-admin-pages` · `observability-error-tracking`. Where the operator sees jobs, queues, provider spend, flags, and errors.
- **Docs/test hygiene (P1/opportunistic):** `refresh-test-suite-doc` · `architecture-doc-stale-execute`.
- **Site-audit runtime & isolation (P3, M3):** `deploy-site-audit-worker` · `site-audit-chromium-image-missing` · `site-audit-egress-isolation` · `site-audit-worker-env-isolation-unbuilt` · `crawler-silent-html-swallow`.
- **Scheduler substrate (P3, M4):** `scheduled-recurring-runs-history` · `tavily-price-unverified-live-cap`.

---

## Implementation order (dependency-resolved batches)

Every item's dependencies appear in an earlier batch (or earlier within the same batch, noted inline). External blockers are marked `[EXT]` and must be started in parallel — see the next section.

**Batch 1 — Stop the bleeding (no deps, fully parallel).**
~~`database-backups`~~ · ~~`cap-container-resources`~~ · ~~`bound-container-logs`~~ · ~~`worker-liveness-healthcheck`~~ · ~~`deep-health-endpoint`~~ · ~~`fix-preflight-key-check`~~ · ~~`harden-rollback-pruned-image`~~ · ~~`ci-validate-prod-compose`~~ · `format-backlog-repo-wide`. Also: ~~gate the Site Audit enqueue in prod~~ (done, ADR-44). Kick off `[EXT]` Stripe account + terms text (#50) procurement now — they gate Batch 3.

***Batch 1 is clear apart from `format-backlog-repo-wide`, which should stay parked*** — CI gates the linter and not the formatter, so a repo-wide `ruff format` would rewrite ~51 files nobody asked to touch and would collide with every open lane. Everything else in the P0 band shipped across sessions 24 and 25.

*What is left of each closed item is written into its row and into tech-debt, and two of those residuals are worth carrying forward rather than forgetting: backups have no **off-box** copy (#79, operator **B13**), and a wedged worker is **detected but not restarted** (#81, because Compose does not restart unhealthy containers). Both are honest partials, not oversights.*

**Batch 2 — M1 lanes open (needs Batch 1).**
First `pre-migration-snapshot` (← `database-backups`), then the M1 work with no intra-M1 code deps, in parallel across lanes: `password-reset-endpoint` · `mfa-totp-and-org-policy` · `session-device-management` · `org-switcher-ui-multi-org-me` · `account-lifecycle-gdpr-owner-transfer` · `workspace-project-api-and-ui` · `platform-back-office` · `feature-flags-system` · `org-api-keys` · `audit-log-csv-export` · `enforce-quota-on-spend-paths` · `auth-endpoint-rate-limiting` · `cap-and-validate-email-columns` · `audit-coverage-public-writes` · `secrets-rotation-procedure` · `observability-error-tracking` · `refresh-test-suite-doc`.

**Batch 3 — M1 items that consume Batch 2 (needs Batch 2).**
`stripe-subscription-lifecycle` (← `enforce-quota-on-spend-paths`; `[EXT]` Stripe + terms) · `system-admin-pages` (← `enforce-quota-on-spend-paths` for spend rollups) · `pii-retention-and-erasure` (← `account-lifecycle-gdpr-owner-transfer`).

**Batch 4 — M1 exit gate (needs all of Phase 7).**
`cross-tenant-leakage-suite` (← `enforce-quota-on-spend-paths`, `platform-back-office`) · `audit-emit-no-outbox` (A9 residual, hardened alongside the suite). **M1 closes here.**

**Batch 5 — M2 Backlink (needs M1 quota/credit + `[EXT]` vendor A4).**
`backlink-inventory-ui-and-api` (can start against the mock in parallel with late Batch 2) → `backlink-vendor-adapter-metered-import` (← quota/credit foundation, `[EXT]` A4) → `backlink-monitoring-scheduled-refresh-liveness` (← adapter + a minimal scheduler seam built here).

**Batch 6 — M3 Site Audit (needs `cap-container-resources`).**
`deploy-site-audit-worker` → then in parallel `site-audit-chromium-image-missing` · `site-audit-egress-isolation` · `site-audit-worker-env-isolation-unbuilt` · `audit-breadth-cwv-hreflang-llmstxt`. Independent of the worker: `crawler-silent-html-swallow` · `csv-xlsx-exports`.

**Batch 7 — M4 Monitoring (needs M1 quota).**
`scheduled-recurring-runs-history` → then `alert-engine-rules-channels-digest` · `project-dashboards-and-weekly-digest` · `local-geo-conditioned-visibility` (`[EXT]` A5).

**Batch 8 — M6 Reporting (needs M4 scheduler).**
`report-builder-pdf-live-link` → `white-label-and-client-portal` (seats already exist from M1 tenancy).

**Batch 9 — M7 Public API (needs M1 keys).**
`publish-api-reference-docs` (← `org-api-keys`).

**Independent lane (any time, operator-gated).**
`tavily-price-unverified-live-cap` (`[EXT]` Tavily invoice) → `public-checker-go-live` (`[EXT]` operator go/no-go). `architecture-doc-stale-execute` and `ci-concurrency-and-paths` slot into any batch as fill.

---

## External dependencies (operator / vendor / legal)

These block kept items and cannot be resolved by engineering. Start them early; several sit on the M1 critical path.

| Blocker | Type | Blocks | Notes |
|---|---|---|---|
| Stripe account (test + live) | Operator | `stripe-subscription-lifecycle` | Needed to create any subscription; admin-panel-plan §10 dependency. |
| Terms-of-service / DPA text (#50) | Legal | `stripe-subscription-lifecycle` (selling), `pii-retention-and-erasure` | On the M1 critical path — a plan cannot be *sold* without it. |
| Backlink vendor contract + budget (decision **A4**) | Operator/Vendor | `backlink-vendor-adapter-metered-import`, and therefore `backlink-monitoring-scheduled-refresh-liveness` | M2 start gate; until then only the mock adapter exists. |
| Local/geo data vendor — grid / AI-Overviews (decision **A5**) | Operator/Vendor | `local-geo-conditioned-visibility` | Raised when the M4 local workstream is reached. |
| Real Tavily invoice / per-search price | Operator | `tavily-price-unverified-live-cap`, and therefore `public-checker-go-live`'s cost cap | No agent can read the invoice; `TAVILY_SEARCH_USD` is a guess that now feeds a live daily cap. |
| Checker launch go/no-go (P5.11) | Operator | `public-checker-go-live` | Independent of M1+; ships any day the operator approves. |
| Site-audit worker deploy topology on the shared VPS | Operator | `deploy-site-audit-worker` / `cap-container-resources` | Whether Chromium runs on-box (capped like searxng) or is moved off-box — a resource-pressure decision, roadmap M3 risk. |

---

## Sizing summary

Counts are of **kept** items (53), after de-duplication.

| Priority | S | M | L | Total | feat | infra |
|---|---|---|---|---|---|---|
| **P0** — blocking / at risk | 5 | 5 | 0 | 10 | 0 | 10 |
| **P1** — M1 (next milestone) | 3 | 14 | 5 | 22 | 11 | 11 |
| **P2** — M2 (milestone after) | 0 | 2 | 1 | 3 | 3 | 0 |
| **P3** — M3–M7 + opportunistic | 4 | 9 | 5 | 18 | 9 | 9 |
| **Total** | **12** | **30** | **11** | **53** | **23** | **30** |

Read plainly: **M1 (P1) is 22 items and the only band with five L's stacked — it is the largest single lift in the queue and should be resourced as such.** P0 is deliberately cheap (five S, five M, no L) so it can be cleared fast and in parallel. The infra track (30 items) slightly outnumbers the feature track (23) — expected for a milestone whose whole thesis is "governance and platform, not dashboards."

---

## What was considered and dropped

**Nothing was dropped as already-implemented.** Every "not done" claim that was doubtful was checked against the code, and all held: `main.py` registers only routes/auth/seo-project/admin/invitation (no billing, backlink, workspace, platform, or system routers); `/healthz` returns a static `{"status":"ok"}`; `auth_routes.py` exposes only signup/login/refresh/logout/me; there are no `mfa`/`totp`, `feature_flags`, or `api_keys` model definitions; `reserve()` is called only from `backlink/delta.py`; `admin_routes.py` has no CSV/export; the prod compose runs only db/api/worker/searxng/web with resource caps and a log cap on searxng alone and a healthcheck on db alone; the Dockerfile is a single `python:3.12-slim` stage with no Chromium; and no `pg_dump`/backup exists anywhere. The M2 backlink cards that *are* done in code (P8.1/P8.5/P8.6/P8.7) never appeared as candidates, so there was no phantom backlog to prune there.

**63 survey entries → 53 kept. 10 were merged out as duplicates or umbrellas** (the sharpest "why" and the combined evidence were carried into the surviving id):

1. `deploy-site-audit-worker` — the same "add the site-audit worker to compose" finding arrived **four** times (`site-audit-worker-not-deployed`, two `deploy-site-audit-worker` entries, and inside the parity survey). Collapsed to one `deploy-site-audit-worker`. (−3 entries)
2. `cross-tenant-leakage-suite` — appeared twice (admin-completion and quality-security), identical intent (the A9 exit gate). Merged. (−1)
3. `auth-completion-reset-mfa-sessions` — an umbrella over `password-reset-endpoint` + `mfa-totp-and-org-policy` + `session-device-management`. Dissolved into those three, which P7.5 lists as distinct shippable pieces. (−1)
4. `enforce-quotas-on-resource-creation` — the same "no quota is enforced on any authenticated spend path" as `enforce-quota-on-spend-paths`, plus the "billing router never included in `main.py`" evidence, which was folded in. Merged. (−1)
5. `site-audit-no-quota` — a specific instance (quota on audit creation) of `enforce-quota-on-spend-paths`, whose own title already names the site-audit submission path. Folded in. (−1)
6. `audit-write-loss-outbox` — the same catch-all-`emit`-swallows-the-event finding as `audit-emit-no-outbox`. Merged (kept `audit-emit-no-outbox`). (−1)
7. `queue-observability` — the jobs/queues board is a strict subset of `system-admin-pages` (§7 system pages). Folded in. (−1)
8. `site-audit-crawler-production-hardening` **and** `harden-site-audit-crawler` — two umbrella framings of the M3 hardening list. Dissolved into the concrete rows they enumerate (`site-audit-egress-isolation`, `site-audit-worker-env-isolation-unbuilt`, `crawler-silent-html-swallow`, plus the quota fold-in), so the work is counted once as separately-shippable PRs rather than as a vague epic. (−2)

Everything else in the survey survived as a distinct, still-open item.
