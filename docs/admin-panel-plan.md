# Yanki — Admin Platform Plan (Milestone M1 — highest priority)

*Audience: founder-orchestrator + implementing agents. This is the complete
plan for Yanki's first platform milestone: the administration system. It is
the **next thing built** (operator directive 2026-08-05; ADR-33). The
engineering decomposition lives as **Phase 7** in
[implementation-plan.md](implementation-plan.md); this document is the spec
those cards point back to. Organizational model and RBAC follow the planning
baseline ([Yanki_Geo_Intelligence_Report.pdf](Yanki_Geo_Intelligence_Report.pdf)
§10–§11), extended with the platform-operator (Super Admin) layer the report
leaves implicit.*

**Status (2026-08-05, session 22): stages A1–A4 are built and merged; A5–A9
are open.** Concretely: tenancy and personal-org backfill (A1, ADR-35), the
ten-role permission model enforced at the API layer (A2), the audit spine with
request identity and tamper evidence (A3, ADR-38/39), and the **Admin Panel**
itself — members, roles, invitations and a queryable audit log (A4, ADR-37).
Still unbuilt: auth completion (A5 — password reset, MFA, session management),
plans/quotas/credit ledger (A6), the platform back office (A7), the system
pages (A8) and the hardening exit gate (A9). §7 of this document is entirely
A7/A8 and none of it exists.

**Nothing in this document is implemented unless the corresponding Phase 7 card
in [implementation-plan.md](implementation-plan.md) says so** — that ledger, not
this paragraph, is the record. The prioritized queue of what remains lives in
[backlog.md](backlog.md).

---

## 1. Why the Admin Platform is first

1. **Every parity milestone depends on it.** Backlinks (M2) needs per-org
   quotas before it can meter a licensed index. Scheduling (M4) needs
   projects to schedule. Reporting (M6) needs workspaces to brand. Nothing
   REQUIRED in [feature-parity.md](feature-parity.md) ships cleanly on top of
   today's "a `users` table and nothing behind it" (tech-debt #52).
2. **The product is already multi-actor.** Two developers merge to `main`
   (which auto-deploys), an operator flips env flags, and PR #11 landed with
   zero documentation. A platform run this way needs feature flags, audit
   trails, and job observability as *operational* tooling, not just as a
   customer feature.
3. **The wedge is structural** (differentiator D4): free client seats,
   workspace-per-client, volume pricing. Those are schema decisions. Getting
   org → workspace → project → subscription → quota right now is cheaper
   than any later migration.

## 2. Scope overview

Two distinct surfaces, one permission model:

- **Platform Admin ("back office")** — for Yanki staff (Super Admin /
  Support): every organization, subscription, flag, queue, provider, and log
  in one place.
- **Organization Admin ("settings")** — for customer org owners/admins:
  their org, workspaces, members, roles, billing, quotas, API keys, audit
  log.

Both read the same underlying services; the difference is scope and role.
Client-facing Viewer/Guest isolation is architectural from day one (separate
lanes; no credit/billing/internal visibility — baseline §11.3).

## 3. Organization management

| Capability | Detail |
|---|---|
| Organizations | CRUD; org = billing + security boundary. Fields: name, slug, logo, region (residency-ready), status (`active/trial/suspended/closed`), created/owner refs. Every tenant-owned row carries `org_id` (RLS-style scoping at the data layer). |
| Workspaces | Org → workspaces (client for agencies; brand/region for multi-location). Branding fields (logo, colors — used by M6 white-label), membership grants. |
| Projects | Workspace → projects (a tracked business: URL/domain, locale, competitor set, prompt panel refs). Existing `analyses` and `seo_projects` rows get org/workspace/project foreign keys via backfill migration (personal-org scaffolding for existing users — baseline §10.4). |
| Subscriptions & plans | Plan catalog as data (Free/Starter/Pro/Business/Enterprise per baseline §12 — tiers configurable, not hardcoded); Stripe subscription lifecycle (trial, active, past_due, canceled); proration; dunning state visible. |
| Billing visibility | Read-only invoices/payment status per org (Stripe-sourced); credit ledger view; spend by workspace/project (the per-response `cost_usd` we already record, finally rolled up). |
| Quotas & limits | Per-plan limits as data: projects, workspaces, paid seats, analyses/month, scan credits, AI credits, API rate. Enforcement = one `quota` service consulted by every spend path (extends the existing rate-limit service pattern). Approaching-limit events (80%) emitted for M4 alerts. |
| Plan management | Admin overrides: extend trial, grant credits, comp a plan, suspend org (read-only mode, export always allowed — "no data hostage-taking"). Every override audit-logged with reason. |

## 4. User management

| Capability | Detail |
|---|---|
| Users | Directory (per-org and platform-wide): profile, verified email, status (`invited/active/deactivated`), last-active, org memberships. Multi-org membership with org switcher (contractor mode, baseline §10.4). |
| Invitations | Email invites with role + workspace scope; expiring single-use tokens; resend/revoke; optional domain auto-join (opt-in, pending-approval). |
| Onboarding | Role capture at first login (agency / multi-location / solo — personalizes defaults); org-creation wizard; personal-org → company-org conversion path (data intact). |
| Lifecycle | Deactivate (retain history, free the seat) vs delete (GDPR path, 30-day soft window); artifact-transfer wizard for departing users (schedules, API keys, reports → successor); exactly-one-Owner invariant with password + email-confirmed transfer. |
| Authentication management | Session/device list per user with remote revoke (the `auth_sessions` family model already supports it); password reset **endpoint** (repays tech-debt #49 — the screen was removed because the endpoint didn't exist; unknown addresses must answer exactly like known ones); breach-password check at set time. |
| MFA management | TOTP enroll/verify/backup codes; admin can *reset* (never read) a member's MFA; org-level "require MFA" policy flag (enforced at login); WebAuthn deferred to M8. |
| Account status | Lock/unlock, forced password reset, sign-out-everywhere (family revocation exists today — expose it). |

## 5. Role & permission system (RBAC)

**Model (baseline §11): `permission = role capability ∩ scope grant` — deny
by default, additive capabilities, enforced at the API layer (UI only
reflects). Client roles structurally isolated.**

Roles (fixed set now; custom roles = clone-and-edit at M8 Enterprise):

| Role | Layer | Summary |
|---|---|---|
| **Super Admin** | Platform | Yanki staff; everything, everywhere; every action audit-logged; cannot be held by customers |
| **Support** | Platform | Read-only platform access + impersonation with consent-and-log |
| **Organization Owner** | Org | Everything in the org incl. delete-org, billing, owner transfer (exactly one) |
| **Admin** | Org | Org management minus delete-org and billing purchase |
| **Billing Admin** | Org | Billing/plan/credits only — finance never needs data access |
| **Manager** | Workspace-scoped | Workspace admin: settings, members ≤ Editor, projects |
| **Editor** | Workspace-scoped | Create/edit projects, run analyses, build/send reports |
| **Analyst** | Workspace-scoped | Run analyses, edit keywords/panels, draft (not send/publish) |
| **Viewer (internal)** | Workspace-scoped | Read dashboards/results; export toggleable |
| **Guest (client)** | Workspace-scoped | Free, unlimited; curated read-only views; client comment lane only; can never see credits, internal notes, other workspaces, or pricing |

Permissions are **resource-based and extensible**: stored as
`resource:action` strings (`project:create`, `report:send`,
`billing:manage`, `apikey:issue`, `audit:read`, …) grouped into the role
templates above, so M2+ modules add `backlink:view` etc. without schema
change. Export is a **distinct permission**. AI actions are twice-gated
(role capability AND per-workspace policy toggle). The full
capability-by-role matrix in baseline §11.2 is adopted as the acceptance
fixture: the permission test suite enumerates that table.

## 6. Audit logs

Append-only `audit_events`, emitted from **every** mutating service from M1
onward (the baseline mandates emission "from MVP even if the viewing UI ships
later" — we are late; M1 pays this down).

Recorded per event: `id`, `occurred_at` (UTC), `actor` (user id / api key id /
`system` / job id), `org_id`, `workspace_id?`, `action` (CRUD verb +
`resource:action` string), `entity_type` + `entity_id` (the affected DB
record), **`before` / `after` values** (JSON diff, secret-redacted),
`ip_hash` (salted, consistent with the existing rate-limit hashing),
`user_agent`, `request_id`, `outcome` (`success/denied/error`).

Event classes covered: logins/logouts/failed logins & MFA events ·
permission and role grants/revokes · every admin override · billing/plan
changes · API-key issue/revoke/use (metadata, not payloads) · data exports ·
webhook config changes · AI publish actions · system actions (migrations
applied, flags flipped, jobs retried) · impersonation start/end.

Admin UX: filter by org/actor/entity/action/date; entity timeline view
("everything that ever touched project X"); before/after diff render; CSV
export (itself audit-logged). Retention: 24 months hot, then archived —
configurable at M8. Integrity: append-only table, no update/delete grants to
app roles; hash-chaining deferred (M8).

## 7. System administration

| Page | Contents |
|---|---|
| **Feature flags** | Global + per-org flags with description, owner, default; kill-switches for every module (the `CHECKER_ENABLED` pattern, generalized and UI-managed); flag flips audit-logged |
| **Settings** | Platform settings currently buried in env (`geo_mode`, caps, cadence defaults) surfaced read-first, then writable where safe; env-only secrets stay env |
| **Integrations** | Status board of connected providers per org (GBP/GSC/Slack later) + platform-level vendor connections |
| **API keys** | Org-scoped keys: issue/rotate/revoke, scopes, per-key rate/spend caps, last-used; hashed at rest (matches session-token discipline) |
| **Background jobs** | The existing Postgres queue (`jobs`, site-audit queue) made visible: queued/running/failed by kind, attempts, durations; retry/cancel with audit; stale-claim reaper status |
| **Queues** | Depth + throughput per pool (analyses, site audits, future scans); pause/resume per pool (flag-backed) |
| **AI providers** | Provider registry status (Anthropic, OpenAI, Gemini, Perplexity, **OpenRouter**, **Tavily**, SearXNG): key-present checks, model + pinned prices, per-provider spend (from `cost_usd` rollups), DRY_RUN/geo_mode visibility, per-provider disable |
| **Webhook management** | (Ships fully in M7) — M1 lays the table: endpoint registry, secret, event subscriptions, delivery log with redrive |
| **Usage analytics** | Org/platform usage: analyses per day, credits burned, active orgs/seats, feature adoption; the funnel events (§7.10 of baseline) once instrumented |
| **Health monitoring** | `/healthz` per service + DB/queue/provider probes on one screen; SearXNG instance health (engine refusal rates — normalizes the "unresponsive_engines is normal" operator duty) |
| **Logs & error tracking** | Structured app-log tail (request_id-linked) + error groups; wire Sentry-class capture (self-hosted GlitchTip acceptable on the shared VPS) |

## 8. Data model (planning sketch — final shape decided at build)

```
organizations(id, name, slug, region, status, owner_user_id, stripe_customer_id, …)
workspaces(id, org_id, name, branding_json, …)
projects(id, org_id, workspace_id, name, url, locale, …)
memberships(id, org_id, user_id, role, status)              -- org-level role
workspace_grants(id, membership_id, workspace_id, role_cap) -- scope grants
invitations(id, org_id, email, role, workspace_ids, token_hash, expires_at, status)
plans(id, key, name, limits_json, price_refs)               -- catalog as data
subscriptions(id, org_id, plan_id, stripe_sub_id, status, period_end, …)
quotas/usage_counters(org_id, metric, window, used, limit)
credit_ledger(id, org_id, delta, reason, actor, balance_after, …)
api_keys(id, org_id, name, hash, scopes, caps_json, last_used_at, revoked_at)
feature_flags(id, key, description, default_on) + org_flag_overrides
audit_events(…see §6…)
webhook_endpoints(id, org_id, url, secret_hash, events, status)
users/auth_sessions: existing tables extended (mfa_secret, status, last_active_at)
analyses/seo_projects: gain org_id/workspace_id/project_id (backfilled)
```

Migration rule: additive + backfill, never destructive; every existing row
lands in a personal org so nothing breaks for current users.

## 9. Build stages (→ Phase 7 cards)

| Stage | Card | Contents |
|---|---|---|
| A1 | P7.1 | Tenancy schema + personal-org backfill + org-scoping of existing reads (the riskiest migration, done first while surface is small) |
| A2 | P7.2 | RBAC: roles/permissions model + API-layer enforcement + permission test suite from the baseline matrix |
| A3 | P7.3 | Audit-event emission service + append-only store (wired into auth + every mutating route as they exist today) |
| A4 | P7.4 | Org admin UI v1: org/workspace/member/invite screens; the first signed-in destination (repays tech-debt #52's product half) |
| A5 | P7.5 | Auth completion: password reset endpoint+screen (#49), MFA (TOTP), session/device management UI, org MFA policy |
| A6 | P7.6 | Plans/subscriptions/quotas: Stripe integration, plan catalog, quota service + enforcement on analysis submission, credit ledger seed |
| A7 | P7.7 | Platform admin (back office): org directory, plan overrides, flags, audit viewer, Support role + logged impersonation |
| A8 | P7.8 | System pages: jobs/queues/providers/health/usage/errors |
| A9 | P7.9 | Hardening pass: permission fuzzing (cross-tenant leakage tests), audit completeness review, docs + ADRs, operator runbook |

Sizing: A1–A3 are the load-bearing 40%; A4–A8 parallelize across lanes
(backend-spine / frontend / infra) once A2's enforcement seam exists.
Estimated complexity: **L (multi-session per stage; 1–2 focused sessions
each for A1–A6 at recent session velocity)**.

## 10. Dependencies, risks, acceptance

**Dependencies:** Stripe account (operator); terms-of-service text before
accounts are *sold* (tech-debt #50 — legal, now on the critical path);
decision on personal-org semantics for the ~existing users; email sending
(exists, Resend).

**Risks:** (1) *Migration on a live DB* — org backfill touches every table;
mitigations: additive migrations, staging rehearsal, ADR-30's
migrate-before-serve already in place. (2) *Permission bugs = tenant
leakage* — the A9 cross-tenant test suite is the exit gate, not optional.
(3) *Scope creep toward customer features* — the admin milestone ships
governance, not dashboards; M4 owns customer-facing analytics. (4)
*Auto-deploy-on-merge with two developers* — feature flags (A7) and the
audit log exist partly to make this safe; until then, sequencing discipline.

**Acceptance (M1 exit):** a new signup lands in an org; can invite a
teammate as Analyst and a client as Guest; Guest provably cannot reach
internal lanes/credits (test-enforced); a plan with limits is purchasable in
Stripe test mode and quota-enforced on submission; every mutating action in
the build appears in the audit log with before/after; Super Admin can find
any org, flip a flag, retry a job, and see provider spend; `make test` green
throughout; zero cross-tenant reads under the A9 suite.

**Explicitly not in M1:** SSO/SCIM (M8) · customer dashboards (M4) ·
white-label (M6) · public API keys' *consumer* docs (M7 — issuing/managing
is M1) · custom roles (M8).
