# Module coupling map

**Status:** Active — Phase A (mod-2)  
**Purpose:** For each monolith pipeline step, record which **product module** owns it, which **external vendor** it calls, which **DB tables** it writes, and whether it **implicitly reads** another module's data.

Parent plan: [standalone-modules-plan.md](./standalone-modules-plan.md)

---

## Monolith pipeline (today)

Entry: `POST /api/v1/analyses` → worker `run_pipeline` / `run_execute_prompts_and_score`

```
discovery → kyc → prompts → execute → footprint (+ SERP) → scoring
                              ↑                           ↑
                         (guided pause)            seo_audit inside discovery
                                                    serp inside footprint
```

---

## Step × module × vendor matrix

| Step | Module | Sync/async | Vendor / engine | Tables written | Reads other modules? |
|------|--------|------------|-----------------|----------------|----------------------|
| **discovery** | KYC (crawl input) + SEO audit | sync in worker | HTTP crawl (own) | `analyses.seo_*`, `seo_checks` | No |
| **kyc** | KYC / brand profile | sync in worker | OpenRouter (analysis LLM) | `analyses.kyc`, `kyc_cost_usd`, `kyc_usage` | Uses discovery text only |
| **prompts** | AI Visibility (prompt set) | sync in worker | None (deterministic templates) | `prompts` | Reads `analyses.kyc` |
| **execute** | AI Visibility (GEO) | sync in worker | OpenRouter; Tavily when measured | `responses`, `geo_records`, `analyses.geo_run` | Reads `prompts`, `kyc` |
| **footprint** | AI Visibility (reliability) | sync in worker | None | `analyses.reliability_score`, `responses.footprint` | Reads `responses` |
| **footprint → SERP** | SERP visibility | sync in worker | SearXNG (`serp/registry.py`) when `SERP_ENABLED=1` | `serp_checks`, `analyses.serp_*` | Reads `kyc`, `prompts` (query text) |
| **scoring** | AI Visibility (aggregate) | sync in worker | None | `analyses.geo_score`, `footprint_count`, `interventions`, `citation_summary` | Reads `responses`, audit blobs |

**Checker branch:** skips discovery crawl + SEO audit; seeds KYC from `brand` + `category`; uses `checker_prompts` instead of `prompts.generate_prompts`.

---

## Already-standalone modules (no analysis job)

| Module | API entry | Vendor | Tables | Triggers analysis pipeline? |
|--------|-----------|--------|--------|----------------------------|
| **Keywords** | `POST /api/v1/keywords/expand`, `/overview`, `/rank-check` | SearXNG + optional Google Ads volume | None (stateless) | No |
| **Backlinks** | `POST …/seo-projects/{id}/backlinks/refresh` | Mock / future DataForSEO | `backlink_*` on project | No |
| **Site audit** | SEO project enqueue routes | Own Chromium worker (partial) | `site_audits`, `site_audit_*` | No |
| **Checker submit** | `POST /api/v1/checker` | — | Creates `analyses` row (`kind=checker`) | Yes — mini pipeline |
| **Waitlist / auth / billing** | various | Resend, OAuth, Stripe-like ledger | tenancy tables | No |

---

## Implicit cross-module reads (must become explicit — mod-7)

| Feature | Location | What it reads today | Target (mod-7) |
|---------|----------|---------------------|----------------|
| **Unlinked mentions** | `backlink/gap.py` | Latest `geo_records.citations` + `serp_checks.matched_url` for project's domain | Caller passes `geo_run_ids[]`, `serp_run_ids[]` |
| **Top cited pages (planned)** | prod-3 | `geo_records` across analyses | Filter by explicit run ids or `brand_context_id` |
| **Guided wizard** | frontend | Full `GET /analyses/{id}` | Compose `/kyc/profiles` + `/ai-visibility/runs` (mod-9) |

---

## Vendor map (current vs target)

| Vendor | Modules using it today | Config | Target swap |
|--------|------------------------|--------|-------------|
| **OpenRouter** | KYC extraction, GEO execute (measured/simulated) | `OPEN_ROUTER_KEY`, `GEO_MODE` | Keep |
| **Tavily** | GEO measured search grounding | `TAVILY_API_KEY` | Evaluate DFS vs Tavily (dfs-8) |
| **SearXNG** | SERP footprint, keyword expand/rank-check | `SERP_ENABLED`, `SERP_PROVIDER=searxng` | DataForSEO Organic SERP (feat branch) |
| **Google Ads API** | Keyword volume (optional) | `KEYWORD_ADS_ENABLED` | DataForSEO Keywords Data API (feat branch) |
| **Mock backlink index** | Backlinks refresh | `BACKLINK_VENDOR=mock` | DataForSEO Backlinks (mod-10, b0–b5) |
| **HTTP crawl** | Discovery, SEO homepage audit | — | Keep (own) |

DataForSEO billing is **per product** — SERP, Keywords, and Backlinks are separate credit pools.

---

## Phase B target: decoupled run types

| New job kind | Module | Replaces (partially) | Must NOT chain |
|--------------|--------|----------------------|----------------|
| `kyc_extract` | KYC | discovery + kyc steps | prompts, execute, serp |
| `geo_run` | AI Visibility | execute + scoring | kyc (optional input only), serp |
| `serp_run` | SERP visibility | footprint SERP half | execute, kyc auto-run |

Bundle orchestrator (`mod-8`) may enqueue multiple kinds in one user action, but each kind is a **separate job record** with its own lifecycle.

---

## Files to touch by phase

| Phase | Primary files |
|-------|-----------------|
| A (done) | `docs/standalone-modules-plan.md`, `docs/module-coupling-map.md`, `db/models.py` (`BrandContext`), `alembic/0026_*` |
| B | `api/routes.py`, `pipeline/runner.py`, `worker.py`, new `api/*_routes.py` per module |
| C | `backlink/gap.py`, bundle flags on `POST /analyses` |
| D | `frontend/app/`, `docs/standalone-modules-plan.md` (deprecation) |
