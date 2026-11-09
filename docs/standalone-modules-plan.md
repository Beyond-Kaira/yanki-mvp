# Standalone modules architecture plan

**Status:** Active — Phase A complete (2026-09-19)  
**Goal:** Each product module (AI Visibility, KYC, SERP, Keywords, Backlinks, Site Audit, …) exposes its own endpoints and job lifecycle. **One module's run must not automatically trigger another.**

The monolithic `POST /api/v1/analyses` pipeline remains supported during transition as an optional **bundle orchestrator**, not the only entry point.

Related:

- [module-coupling-map.md](./module-coupling-map.md) — pipeline step × module × vendor matrix (mod-2)
- [dataforseo-touchpoint-map.md](./dataforseo-touchpoint-map.md) — DataForSEO product boundaries per module
- [design.md § ADR-52](./design.md#adr-52--standalone-module-runs-no-auto-trigger-2026-09-19-mod-0) — decision record

---

## Problem today

`POST /api/v1/analyses` enqueues a single worker job that runs:

```
discovery → kyc → prompts → execute (GEO) → footprint (+ SERP) → scoring
```

Implications:

- Starting AI Visibility **always** runs KYC, prompt generation, and optionally SERP visibility in the same job.
- SERP visibility runs inside the **footprint** step when `SERP_ENABLED=1` — not independently callable.
- KYC is both the **entry point** for guided flows and a **pipeline step** — hard to expose as a standalone product surface.
- Cross-module features (e.g. backlink `unlinked_mentions`) **implicitly read** other modules' DB rows (`geo_records`, `serp_checks`) without explicit run references.

---

## Target architecture

### Shared context (optional link, not auto-trigger)

```
BrandContext
  brand, domain, locale, category, competitors[], org_id, source_url, profile (KYC-shaped JSON)
```

Modules **may reference** a `brand_context_id` but never require another module's run to have succeeded.

### Per-module run pattern

Each module follows the same shape:

| Concern | Pattern |
|---------|---------|
| Create | `POST /api/v1/{module}/runs` → `202` + `run_id` |
| Poll | `GET /api/v1/{module}/runs/{run_id}` |
| Result slice | `GET /api/v1/{module}/runs/{run_id}/{artifact}` (e.g. `/geo`, `/checks`) |
| Worker | Dedicated job type or queue — **no chained steps from other modules** |
| Billing | Per-module quota / cost attribution |

### Cross-module analytics (opt-in only)

Features that combine data from multiple modules (e.g. unlinked mentions, future dashboards) become **explicit join endpoints**:

```
POST /api/v1/outreach/unlinked-mentions
  { brand_context_id, geo_run_ids[], serp_run_ids[] }
```

No silent reads of "whatever analyses exist for this domain."

---

## Module inventory

| Module | Standalone today? | Current entry | Target standalone API | Data vendor |
|--------|-------------------|---------------|----------------------|-------------|
| **Keywords** | Yes | `POST /keywords/expand`, `/overview`, `/rank-check` | Keep (stateless / sync) | SearXNG today; DataForSEO Keywords (planned) |
| **Backlinks** | Yes | `POST …/backlinks/refresh` on SEO project | Keep; document contract | Mock index today; DataForSEO Backlinks (planned) |
| **AI Visibility (GEO)** | No | `POST /analyses` → execute step | `POST /ai-visibility/runs` | OpenRouter + Tavily (measured) / simulated |
| **KYC / brand profile** | Partial | `GET/PATCH /analyses/{id}/kyc` | `POST/GET /kyc/profiles` | Own LLM / crawl |
| **SERP visibility** | No | footprint step in analysis | `POST /serp/runs` | SearXNG today; DataForSEO Organic SERP (planned) |
| **Site audit** | Partial | SEO project routes (worker not deployed) | `POST /site-audit/runs` | Own Chromium crawl |
| **Checker** | Bundle | `POST /checker` | Optional: `POST /checker/runs` | Same as GEO subset |
| **Prompt tracking** | No | Re-run full analysis | `POST /prompt-tracking/campaigns` | Scheduled GEO runs |

**Reference pattern:** Keywords and Backlinks — already module-scoped routers, kill switches, no analysis pipeline dependency for the **write** path.

---

## KYC vs AI Visibility split

KYC today is the guided-flow entry point but structurally it is **brand context extraction**, not "visibility measurement."

**Target split:**

1. **`BrandContext`** — durable profile: company name, category, competitors, locale, source URL. CRUD via `/kyc/profiles` or `/brand-contexts`. **Phase A:** `brand_contexts` table + optional `analyses.brand_context_id` link.
2. **`AiVisibilityRun`** — prompt set + LLM fan-out + audit. Input: optional `brand_context_id` + explicit prompts (or prompt template id).
3. **Guided wizard (UI only)** — creates BrandContext, then optionally starts AiVisibilityRun; **two API calls**, one UX flow.

Migration: existing `analyses.kyc` JSON blob maps to BrandContext over time; `analysis_id` remains a legacy bundle id until deprecated (mod-12). One-off link: `scripts/backfill_brand_contexts.py` (item 18).

### KYC profiles API — create vs extract (item 19)

| Path | When | Behavior |
|------|------|----------|
| `POST /api/v1/kyc/profiles` with **`source_url`** | User has a URL | **Synchronous** discovery + LLM KYC in the request; writes `brand_contexts` row. Does **not** enqueue GEO/SERP/other modules (ADR-52). |
| `POST /api/v1/kyc/profiles` **without** `source_url` | Manual brand fields only | Creates profile from `brand` + allowlisted KYC patch fields; no crawl. |
| `POST …/kyc/profiles/{id}/extract` | Re-run or first crawl for an existing profile | **Async** `kyc_extract` module job (`202` + `ModuleRunOut`); poll `GET /api/v1/background-jobs/{id}`. Requires `source_url` in body or on the profile. |

PATCH updates fields only — never auto-starts visibility runs.

---

## DataForSEO per module

DataForSEO is **not one API** — plan separate adapters:

| Module | DataForSEO product | Notes |
|--------|-------------------|-------|
| SERP visibility | Organic SERP API | Replaces SearXNG (`dfs-*` tasks) |
| Keywords | Keywords Data API | expand, overview, rank-check |
| Backlinks | Backlinks API | `referring_domains`, `summary`, history — replaces mock index |
| AI Visibility | — | No DFS product; keep OpenRouter/Tavily |
| KYC | — | Own pipeline |
| Traffic & Market | — | Not in scope; separate licensing decision |

Backlinks index is **separate billing** from SERP. Implement `app/backlink/dataforseo.py` when `BACKLINK_VENDOR=dataforseo`.

See [dataforseo-touchpoint-map.md](./dataforseo-touchpoint-map.md) for file-level touchpoints.

---

## Phased rollout

### Phase A — Document & model (no breaking changes) ✅

- [x] `mod-0` This doc + ADR-52 in `docs/design.md`
- [x] `mod-1` BrandContext entity + migration (nullable link from analyses)
- [x] `mod-2` Coupling map: which pipeline steps touch which vendors

### Phase B — Standalone run APIs (parallel to monolith)

- [x] `mod-3` `POST/GET /api/v1/serp/runs` + `GET …/checks` (live DataForSEO smoke: item 15)
- [x] `mod-4` `POST/GET /api/v1/ai-visibility/runs` + `GET …/geo`
- [x] `mod-5` `POST/GET/PATCH /api/v1/kyc/profiles` + `POST …/extract` → `kyc_extract`
- [x] `mod-6` Worker job types: `serp_run`, `geo_run`, `kyc_extract` (separate from `analysis` kind)

**Shared poll:** `GET /api/v1/background-jobs/{id}` for any module job (`ModuleRunOut`). Feature routes also expose poll + artifact slices.

### Phase C — Opt-in cross-module & bundle

- [x] `mod-7` `unlinked_mentions` → `GET …/opportunities?analysis_ids=&module_run_ids=` (explicit evidence)
- [x] `mod-8` `POST /analyses` → optional `steps` + `brand_context_id` (`analyses.bundle_steps`)
- [x] `mod-10` DataForSEO Backlinks adapter seam (`BACKLINK_VENDOR=dataforseo`; live fetch TBD)

### Phase D — Product surface

- [x] `mod-9` Frontend wizard: `/ai-visibility/wizard` (profiles → ai-visibility runs → poll)
- [x] `mod-11` `POST/GET /api/v1/site-audit/runs` + Redis dispatch hint (rq-5)
- [x] `mod-12` Deprecation timeline — see below

### Deprecation timeline (mod-12)

| Milestone | Target | Meaning |
|-----------|--------|---------|
| **Now – Q4 2026** | Dual entry | `POST /analyses` bundle + standalone module APIs both supported |
| **Next** | Client migration | New UI uses `/kyc/profiles`, `/ai-visibility/runs`, `/serp/runs`, `/background-jobs/{id}` |
| **Later** | Bundle optional | `POST /analyses` becomes explicit step flags only; no implicit cross-module reads |
| **TBD** | Legacy read-only | `analysis_id` URLs remain for shared links; new writes prefer module runs |

Communicate breaking changes ≥ one release ahead in API changelog / customer notes.

### Phase Q — Redis queue (hybrid, optional)

**Principle:** Redis/Valkey holds **dispatch pointers only** (`run_id` / `analysis_id`).
Postgres keeps **run state** (`module_runs`, `analyses`), artifacts, audit, and poll APIs.
When `REDIS_URL` is unset, behaviour falls back to today's Postgres `claim_next` path.

| ID | Task | Status (Oct 2026) |
|----|------|-------------------|
| `rq-0` | ADR — hybrid queue, at-least-once, fallback rules | **Done** (ADR-54) |
| `rq-1` | Valkey/Redis in `deploy/docker-compose.yml` + `Settings.redis_url` | **Done** (main) |
| `rq-2` | Broker facade `app/jobs/broker.py` → `redis_dispatch_queue` | **Done** |
| `rq-3` | Wire `module_runs` enqueue + worker (`queue:module`) | **Done** |
| `rq-4` | Monolith `analyses` queue Redis dispatch | **Done** (main; before rq-3) |
| `rq-5` | Site audit `queue:site_audit` LPUSH + worker hint | **Done** |

**Recommended order:** [standalone-modules-implementation-order.md](./standalone-modules-implementation-order.md) — Phase B APIs shipped (Oct 2026); next **Phase C/D** (mod-7+, frontend wizard, site audit queue).

Progress canvases: `standalone-modules-progress.canvas.tsx`, `standalone-modules-action-plan.canvas.tsx`.

---

## Non-goals (for now)

- Rewriting all historical `analysis_id` foreign keys in one release
- Removing the bundle pipeline before standalone paths are production-ready
- Implicit auto-refresh ("run GEO whenever KYC updates")
- Auto-populating `brand_context_id` on every existing analysis row (lazy migration only)

---

## Open questions

1. **Shared project scope** — BrandContext at org level vs SEO project level (today SEO projects exist for backlinks/site audit).
2. **Checker** — separate run type or special case of AiVisibilityRun with fixed prompt template?
3. **Quota model** — per-module caps vs unified "credits" pool.
4. **Frontend routing** — `/ai-visibility/*` vs `/analyses/[id]` during transition.

---

## Task IDs (roadmap tracker)

See Jira workstream **standalone** — prefix `mod-*` / `rq-*`. Progress: `canvases/standalone-modules-progress.canvas.tsx` · sprint steps: `standalone-modules-action-plan.canvas.tsx`.
