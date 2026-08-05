# Yanki — Product Roadmap (platform edition)

*Audience: leadership + engineers. This is the **product** roadmap: the
milestone path from today's live MVP to the Geo Intelligence platform. It
**supersedes** the MVP-era roadmap (Now/Next/Later, in git history) as of
**2026-08-05** — ADR-33 records the decision. The strategy source is
[Yanki_Geo_Intelligence_Report.pdf](Yanki_Geo_Intelligence_Report.pdf) ("the
planning baseline", Aug 2026); the parity evidence is
[feature-parity.md](feature-parity.md); the engineering decomposition lives
in [implementation-plan.md](implementation-plan.md) (milestones map to
implementation phases — table below). This file is the what/why/when, not
the how.*

**The implementation order is fixed (operator directive, 2026-08-05):**

1. **Admin Panel** (M1)
2. **Backlink Intelligence** (M2)
3. **Remaining core feature parity** (M3–M6)
4. **Differentiating features** (M7, woven earlier where free)
5. **Long-term enterprise capabilities** (M8, then M9)

---

## Where we are (2026-08-05, honest snapshot)

**Live in production** (yanki.beyondkaira.com): anonymous URL → GEO analysis
(discovery → KYC → prompts → execute → footprint → score) with grounded
measured mode (Tavily search + OpenRouter answer + citation records — PR #11,
merged 2026-08-04, *undocumented*, tech-debt #54), SERP visibility via
self-hosted SearXNG (ADR-28/29), SEO/AI-readiness audit A–F (ADR-31),
waitlist + transactional email. **Built, dark:** the free public checker
(P5.11 go-live is the operator's). **Merged, unwired:** Site Audit
projects/APIs + Chromium crawler (PR #23, its worker still absent from the
prod compose, hardening unresolved — #55); interventions library + reliability
auditor (PR #11, no UI).

*Updated at session 22 close.* **Shipped since this snapshot was first
written:** organizations and tenancy, RBAC (ten roles, deny-by-default,
enforced at the API), audit logs (emitted, queryable, tamper-evident), and the
**Admin Panel** — so tech-debt #52's "an account grants nothing" is repaid:
signing in now lands somewhere that does something. **Built but not a product
yet:** the backlink engine (delta, authority, toxicity, gap) exists behind a
flag with no API router and no UI; plans/quotas/credit ledger exist as tables
and a service with nothing enforcing them on a spend path. **Still missing
entirely:** billing lifecycle, scheduling, history, dashboards, reports,
alerts, keywords, rank tracking, integrations, public API. The asymmetry this
roadmap fixes — a strong measurement engine with no platform around it — is
narrower than it was, and still real.

## Milestone map at a glance

| Milestone | Theme | Implementation phase | Order |
|---|---|---|---|
| **M1** | Admin Platform (orgs, RBAC, billing, audit, system admin) | Phase 7 | 1 — next build |
| **M2** | Backlink Intelligence | Phase 8 | 2 |
| **M3** | Technical SEO & Site Audit productization | Phase 9 | 3 |
| **M4** | AI Visibility & GEO monitoring (recurring, scored, alerted) | Phase 10 | 4 |
| **M5** | Entity & Local Intelligence | Phase 11 | 5 |
| **M6** | Competitive Intelligence & Reporting | Phase 12 | 6 |
| **M7** | Automation & Agent Platform | Phase 13 | 7 |
| **M8** | Enterprise | Phase 14 | 8 |
| **M9** | Advanced AI (prediction, autonomy, data network) | Phase 15 | 9 |

*(The re-planning brief's "Phase 1…Phase 9" = M1…M9 here. Implementation-plan
phase numbers continue from the existing Phase 0–6 — IDs are never renumbered
in this repo.)*

Cross-milestone rule: **the checker go-live (P5.11) stays operator-gated and
independent** — it can ship any day and none of M1+ blocks it. Turkish
remains parked on the operator's word (unchanged directive, 2026-07-10);
M8's localization work is where it revives naturally if called.

---

## M1 — Admin Platform *(full plan: [admin-panel-plan.md](admin-panel-plan.md))*

> **Two names, one milestone, and they are not synonyms.** The **Admin Panel**
> is the shipped user-facing surface at `/admin` — members, roles, invitations,
> audit log — and that is what it is called everywhere in the product: nav,
> page title, breadcrumb, route. The **Admin Platform** is this milestone, which
> is larger: it also covers billing, plans, quotas, the Yanki-staff back office
> and the system pages, none of which are part of the customer's Admin Panel.
> Stages A1–A4 (the Panel and everything under it) shipped 2026-08-05.

- **Objectives:** turn "a users table" into a governed multi-tenant B2B
  platform: organizations → workspaces → projects; granular resource-based
  RBAC (Super Admin → Guest); complete audit logging with before/after
  values; subscriptions/plans/quotas/credit metering (Stripe); MFA + session
  management; platform back office (flags, jobs, queues, AI providers,
  webhooks table, usage, health, logs/errors).
- **Deliverables:** tenancy schema + backfill; RBAC enforcement at API layer
  + permission suite; `audit_events` emitted from every mutating path; org
  admin UI (first signed-in destination — repays #52); auth completion
  (password reset #49, MFA); plan/quota/credit services; platform admin
  back office; hardening pass (cross-tenant leakage suite).
- **Dependencies:** Stripe account; terms text (#50 — legal, now
  critical-path); operator ratification (operator-expected A3).
- **Risks:** live-DB backfill; permission bugs = tenant leakage (exit-gated
  by test suite); scope creep into customer dashboards (M4's job).
- **Complexity: L** (9 stages, A1–A9).
- **Order: 1 — the foundation every later milestone consumes.**

## M2 — Backlink Intelligence *(full plan: [backlink-intelligence-plan.md](backlink-intelligence-plan.md))*

- **Objectives:** a Ring-1-class backlink module on licensed data: discovery,
  monitoring, new/lost, toxic scoring + disavow, referring domains, anchors,
  transparent authority metrics, velocity, competitor profiles, gap analysis,
  outreach lists, alerts, history, filtering, exports, report blocks.
- **Deliverables:** `BacklinkSource` seam (mock + first vendor adapter),
  metered imports, inventory/anchor/domain UIs, delta engine with verified
  losses, Yanki Authority (published formula), gap/outreach, disavow export.
- **Dependencies:** M1 quotas/credits; vendor contract + budget (operator
  A4); minimal scheduling if M4 hasn't landed.
- **Risks:** vendor COGS drift; freshness disputes vs Ahrefs; storage
  growth; toxicity over-claiming (advisory framing).
- **Complexity: M–L** (8 stages, B1–B8).
- **Order: 2.**

## M3 — Technical SEO & Site Audit productization

- **Objectives:** promote the merged-but-invisible Site Audit backend
  (PR #23) into a customer-grade technical SEO module, and close the crawl
  gaps that block scale.
- **Deliverables:** Site Audit UI (projects, runs, findings, health trend);
  crawler production hardening — the unresolved list in
  [site-audit-integration.md](site-audit-integration.md) (egress isolation,
  non-root Chromium, transfer budgets, retries, quotas, migration gate,
  deploy verification); audit breadth to parity (Core Web Vitals,
  broken-link/redirect-chain depth, hreflang, llms.txt — repays #48);
  indexing: GSC OAuth read + index-status reporting; CSV/XLSX exports;
  audit sections registered for the future report builder.
- **Dependencies:** M1 (projects are org-scoped; audits quota-metered);
  Google OAuth app verification (operator); the site-audit worker actually
  deployed (deploy topology decision — it is not in the prod compose today).
- **Risks:** Chromium-on-shared-VPS resource pressure (capped like SearXNG,
  or moved off-box); crawl abuse against third-party sites (quotas, robots
  discipline — already strong).
- **Complexity: M.** **Order: 3.**

## M4 — AI Visibility & GEO Monitoring (the product becomes recurring)

- **Objectives:** from one-shot analyses to tracked visibility: prompt
  panels, schedules, history, scores users can defend, alerts, dashboards —
  the retention engine. Workstream 2 opens the **local/geo dimension** (the
  baseline's hero bet) at beta depth.
- **Deliverables:** editable versioned prompt panels per project; scheduled
  runs (weekly/monthly cadences, quota-aware) on the existing queue;
  time-series rank/score storage + trend UI; weighted AI Visibility Score
  0–100 (mention × position × sentiment — published formula) beside the
  primitive score; per-engine presence over time (multi-engine panel
  restored as a product surface alongside the measured path); AI-SoV vs
  competitors; citation trends + drill-down; sampling honesty (repeat
  samples, variance disclosure) with the reliability auditor surfaced
  (differentiator D2); insight feed wired to the interventions library;
  alert engine (rules, thresholds, email/Slack/in-app, digests, dedup,
  quiet hours); project/workspace dashboards; weekly digest email;
  **local-AIV beta:** location-conditioned prompt sampling ("dentist near
  X"), AI-SoLV per location, and the geo-grid/AI-Overviews vendor decision
  (operator A5 when reached).
- **Dependencies:** M1 (projects/quotas); LLM cost model per cadence;
  SERP/AI-Overviews data vendor for the local workstream.
- **Risks:** recurring-run COGS (credit allowances + caps from M1);
  AIV sampling credibility (variance disclosure, never single-sample
  claims); alert fatigue (digest/dedup by design).
- **Complexity: L.** **Order: 4 — the largest customer-visible milestone.**

## M5 — Entity & Local Intelligence

- **Objectives:** own the entity layer AI engines read from: canonical
  brand records, knowledge-surface monitoring, and the local stack
  (GBP, citations, reviews).
- **Deliverables:** canonical entity record per project (KYC promoted to a
  maintained profile with owner-confirmed NAP/attributes); knowledge-panel /
  Wikipedia/Wikidata presence checks; entity-consistency diffing (site ↔
  listings ↔ AI answers); GBP OAuth (locations, reviews, insights, posting
  later); local citation monitoring (~top-40 directories, accuracy diffs);
  review ingestion + sentiment + alerts + AI reply drafts
  (approval-gated, brand-voice); local audit flavor (GBP completeness,
  NAP, local schema); schema/entity recommendations from existing
  validator data.
- **Dependencies:** M1; GBP API approval/quota (operator); M4 alerts.
- **Risks:** GBP API access terms; citation-source scraping fragility
  (top-40 curated set, partner data later); review-reply publish safety
  (twice-gated per RBAC design).
- **Complexity: M–L.** **Order: 5.**

## M6 — Competitive Intelligence & Reporting

- **Objectives:** the daily strategy layer: keywords, rank tracking, SERP
  intelligence, competitor tracking — and the agency deliverable: white-
  label reporting. Completes core parity.
- **Deliverables:** keyword research on licensed data (volumes/difficulty/
  intent; local suggestions from the existing topic engine); organic rank
  tracking per keyword × location × device with SERP-feature capture;
  SERP history; named-competitor tracking over time with side-by-side and
  gap views (keywords + visibility + backlinks via M2); content
  intelligence v1 (question/content gaps from citations + SERP data);
  Share of Voice across surfaces — first **Unified Visibility Index**
  release (grid beta + organic + AI, configurable weights); report builder
  (modular sections from M2–M6 blocks, AI-drafted commentary
  human-edited, PDF + revocable live links, schedules); white-label
  (logo → theme → custom domain/from-address); client portal seats
  (Guest role from M1).
- **Dependencies:** M1 seats/branding; M4 time-series + schedules; keyword
  data license (operator decision); M2 for link blocks.
- **Risks:** rank-tracking COGS at cadence (credit model); keyword-license
  terms; report-render isolation (headless service — architecture-target).
- **Complexity: L.** **Order: 6 — closes the parity backlog.**

## M7 — Automation & Agent Platform *(differentiators begin)*

- **Objectives:** the moat the baseline names "prescriptive automation and
  agent-readiness": the platform acts, not just reports — and agents can
  operate it safely.
- **Deliverables:** playbooks (trigger → conditions → actions: task, draft,
  rescan, notify, webhook) with template gallery (D1); insight→action→
  verification loop recording outcomes (the future prediction dataset);
  public API v1 (org-scoped keys from M1, OpenAPI published, rate limits)
  then write endpoints + webhooks; **MCP server** exposing scoped
  capabilities with human-approval modes (D5); llms.txt + machine-readable
  docs; integrations: Slack (if not earlier), Zapier, Looker Studio
  connector; AI content generation (briefs, local pages, GBP posts,
  replies) with EU AI Act Art. 50 labeling (D9); comments/tasks on
  evidence (lightweight collaboration).
- **Dependencies:** M1 audit/keys (agent governance); M4 events/alerts
  (triggers); M6 reports (report-compile API).
- **Risks:** automation safety (approval gates, per-key caps, kill
  switches — designed in M1); integration maintenance surface.
- **Complexity: M–L.** **Order: 7.**

## M8 — Enterprise

- **Objectives:** unlock the security-review buyer without bloating the
  core (the baseline's explicit sequencing).
- **Deliverables:** SSO (SAML/OIDC) + SCIM; org-visible audit log with
  retention controls + integrity hardening; custom roles (clone-and-edit);
  data residency options (EU/TR — the `region` field placed in M1 pays
  off); DPA templates + sub-processor list; SOC 2 Type I program → Type
  II path; listings sync via aggregator partner (the deferred local
  enterprise ask); log-file analysis; volume/enterprise plans + invoicing;
  localization revival path (TR/DE/AR UI + reports) **if the operator
  calls it**; uptime SLAs + status page.
- **Dependencies:** M1 foundations; audit firm; aggregator contract;
  legal budget.
- **Risks:** compliance cost/distraction (separate lane, not the PLG
  core); aggregator economics.
- **Complexity: M–L (mostly process + hardening).** **Order: 8.**

## M9 — Advanced AI

- **Objectives:** the data-moat features nobody can copy without the data.
- **Deliverables:** predictive visibility modeling (action → forecast
  lift, ranges + backtests, D7) on the M7 outcome dataset; autonomous
  monitoring agents (triage + propose + approve, D6); the local AIV data
  network + benchmark reports (D8); playbook marketplace; reseller/API
  platform packaging.
- **Dependencies:** 12+ months of cross-org outcome data (starts accruing
  at M4/M7 — a reason not to delay them); M8 governance for anonymization.
- **Risks:** model-quality bar (ranges, never point promises — trust
  brand); marketplace/reseller legal terms.
- **Complexity: L.** **Order: 9.**

---

## Parity coverage guarantee

Every category in the re-planning brief maps to exactly one milestone —
the table lives in [feature-parity.md](feature-parity.md) §4. If a proposed
feature has no milestone home, it goes to the backlog, not the sprint —
scope discipline unchanged from the MVP era.

## Standing gates

- **Checker go-live (P5.11):** operator's, any time, independent of M1+.
- **M1 start:** operator ratifies this roadmap (A3). **M2 start:** backlink
  vendor + budget (A4). **M4 local workstream:** grid/AI-Overviews vendor
  decision (A5, raised when reached).
- **Per-milestone exit:** acceptance criteria in each plan doc; docs +
  ADRs current; `make test` green; no cross-tenant leakage regressions.
- **Pricing changes** ride M1 (plans-as-data) but public price points are
  operator decisions at each launch moment.
