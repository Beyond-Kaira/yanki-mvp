# SearXNG / SERP touchpoint map

**Task:** `dfs-1` — map every place SearXNG is used before the DataForSEO swap.  
**Date:** 2026-09-14  
**Scope:** runtime code paths, config, deploy, tests, CI, frontend consumers.  
**Out of scope:** Tavily (measured GEO search), simulated GEO (no live search), backlink vendors.  
**See also:** [standalone-modules-plan.md](./standalone-modules-plan.md) — decouple SERP/GEO/KYC into separate run APIs.

---

## Executive summary

SearXNG is the **only live SERP backend** today. It feeds two product surfaces:

1. **SERP visibility** — optional step inside the analysis pipeline (`SERP_ENABLED`).
2. **Keyword research preview** — expand, overview, rank-check APIs (`KEYWORD_ENABLED` + `SERP_BASE_URL`).

Both paths share the same adapter (`SearxngSource`) and the same operator-run container (`deploy/searxng/`). DataForSEO replaces the adapter layer; the pipeline and API shapes can stay if `SerpSource` / `KeywordSource` interfaces are preserved.

| Area | Files / touchpoints | Swap action | Priority |
|------|---------------------|-------------|----------|
| SERP adapter | `backend/app/serp/searxng.py` | New `dataforseo.py`; retire or gate SearXNG | **P0** |
| SERP registry | `backend/app/serp/registry.py` | `SERP_PROVIDER=dataforseo \| searxng` | **P0** |
| SERP interface | `backend/app/serp/base.py` | Keep `SerpSource` / `SerpPage`; map DFS response | **P0** |
| Analysis pipeline | `backend/app/pipeline/serp_visibility.py`, `runner.py` | No direct SearXNG import; uses registry | **P0** (via adapter) |
| Keyword expand | `backend/app/keyword/searxng_expand.py`, `registry.py` | New DFS keyword/suggestions source | **P0** |
| Keyword rank check | `backend/app/keyword/rank_check.py` | Same `SerpSource.search()` | **P1** |
| Config | `backend/app/config.py`, `deploy/.env.example` | `SERP_*` → `DATAFORSEO_*` | **P0** |
| Deploy | `deploy/docker-compose*.yml`, `deploy/searxng/` | Remove or profile-gate SearXNG service | **P1** |
| API (read) | `backend/app/api/routes.py`, `analysis_slices.py` | Unchanged; reads stored `serp_*` columns | — |
| API (keyword) | `backend/app/api/keyword_routes.py` | Unchanged; uses keyword registry | **P0** (via registry) |
| DB | `analyses.serp_*`, `serp_checks` (migration `0007`) | Keep schema; `serp_source` records provider name | — |
| Tests | `backend/tests/serp/`, `tests/keyword/`, `tests/integration/` | Add DFS mocks; gate legacy SearXNG | **P1** |
| CI | `.github/workflows/serp.yml` | Update or legacy-flag SearXNG stack jobs | **P1** |
| Frontend | `SerpVisibility.tsx`, analysis/checker pages | Display only; no SearXNG client | — |
| Docs | `docs/design.md`, `operator-expected.md`, ADR-28/29 | Update operator runbooks | **P1** |

---

## 1. Core adapter layer

### 1.1 `backend/app/serp/searxng.py` — **primary integration**

- Implements `SearxngSource` (`name = "searxng"`).
- Calls SearXNG JSON API: `GET {SERP_BASE_URL}/search?q=…&format=json`.
- Parses organic results, suggestions, PAA-style strings, unresponsive engines.
- Raises `SerpUnavailable` on misconfiguration (no URL, non-JSON response, HTTP errors).

**DataForSEO target:** new module implementing the same `SerpSource` protocol.

### 1.2 `backend/app/serp/registry.py` — **source selection**

- `get_serp_source(settings)` → `None` | `MockSerpSource` (DRY_RUN) | `SearxngSource` (live).
- Gated by `SERP_ENABLED` + non-empty `SERP_BASE_URL`.
- **Only place** the analysis pipeline obtains a SERP reader.

**DataForSEO target:** branch on `SERP_PROVIDER` (or replace `SERP_BASE_URL` with DFS credentials).

### 1.3 `backend/app/serp/base.py` — **shared contract**

- Defines `SerpSource`, `SerpPage`, `SerpResult`, `SerpUnavailable`.
- Documents measurability rules (empty page ≠ miss).
- Comments reference SearXNG JSON/suggestion fields — update when mapping DFS fields.

### 1.4 `backend/app/serp/mock.py`

- DRY_RUN / CI deterministic source. **Keep**; not SearXNG-specific.

---

## 2. Analysis pipeline (SERP visibility)

### 2.1 `backend/app/pipeline/serp_visibility.py`

- Runs during the **footprint** step (not a separate pipeline step).
- Builds brand-neutral queries from `prompts.topic_pool`.
- Calls `SerpSource.search()` up to `SERP_QUERY_COUNT` times (default 6).
- Scores domain/text hits via `footprint.detect`; writes `serp_checks` rows.
- Sets `analyses.serp_score`, `serp_hit_count`, `serp_query_count`, `serp_status`, `serp_source`.
- Fail-open: SERP outage → null score, job continues.

**SearXNG coupling:** docstring + behavior assume metasearch instance; no direct import of `searxng.py`.

### 2.2 `backend/app/pipeline/runner.py`

- Lines ~129–136: `serp_registry.get_serp_source(settings)` → `serp_step.run_serp(...)`.
- Clears `serp_*` on rerun (lines ~89–93, ~195–199).

**DataForSEO:** no runner change if registry returns DFS adapter.

### 2.3 Database — migration `0007_serp_visibility.py`

- Columns: `analyses.serp_score`, `serp_hit_count`, `serp_query_count`, `serp_status`, `serp_source`.
- Table: `serp_checks` (per-query evidence).

**DataForSEO:** schema unchanged; `serp_source` may become `"dataforseo"`.

---

## 3. Keyword research preview

### 3.1 `backend/app/keyword/searxng_expand.py`

- `SearxngKeywordSource` wraps `SearxngSource`.
- One SearXNG round-trip per expand: seed SERP + title-derived related phrases + variants.
- Used for **expand** and **overview** API routes.

### 3.2 `backend/app/keyword/registry.py`

- `get_keyword_source()` → `SearxngKeywordSource(SearxngSource(...))` when live.
- `get_keyword_serp_source()` → raw `SearxngSource` for rank-check.
- Gated by `KEYWORD_ENABLED` + `SERP_BASE_URL` (does **not** require `SERP_ENABLED`).

### 3.3 `backend/app/keyword/rank_check.py`

- On-demand domain position check via `SerpSource.search()`.
- Reuses `site_hosts()` from `serp_visibility`.
- Budget: `KEYWORD_RANK_MAX_QUERIES` (default 10).

### 3.4 `backend/app/keyword/signals.py`

- Filters SERP-host fragments from keyword ideas (`google.com`, etc.).
- Uses `seed_serp_page` for difficulty heuristics — provider-agnostic.

### 3.5 `backend/app/api/keyword_routes.py`

| Route | Registry call | SearXNG path |
|-------|---------------|--------------|
| `POST /api/v1/keywords/expand` | `get_keyword_source()` | expand |
| `POST /api/v1/keywords/overview` | `get_keyword_source()` | expand (thin) |
| `POST /api/v1/keywords/rank-check` | `get_keyword_serp_source()` | rank check |

Dark when `KEYWORD_ENABLED=0` (404).

**Note:** Google Ads metrics (`keyword/metrics/`) are separate — not SearXNG.

---

## 4. Configuration & environment

### 4.1 `backend/app/config.py` (Settings)

| Setting | Default | Used by |
|---------|---------|---------|
| `serp_enabled` | `False` | SERP visibility pipeline |
| `serp_base_url` | `""` | SearxngSource URL |
| `serp_query_count` | `6` | serp_visibility |
| `serp_timeout_seconds` | `10.0` | SearxngSource |
| `serp_language` | `"en"` | SearxngSource |
| `serp_categories` | `"general"` | SearxngSource |
| `serp_engines` | `""` | SearxngSource allowlist |
| `serp_safesearch` | `0` | SearxngSource |
| `serp_max_results` | `20` | SearxngSource |
| `keyword_enabled` | `False` | keyword routes |
| `keyword_max_ideas` | `50` | expand |
| `keyword_variant_max` | `3` | expand |
| `keyword_rank_max_queries` | `10` | rank-check |

### 4.2 `deploy/.env.example`

- Documents `SERP_*` block (lines ~207–251) and keyword preview (lines ~253+).
- Opt-in: `COMPOSE_PROFILES=serp`, `SERP_ENABLED=1`, `SERP_BASE_URL=http://searxng:8080`.

**DataForSEO target:** `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD` (or API key), location/locale params.

---

## 5. Deploy & infrastructure

### 5.1 `deploy/docker-compose.yml` (dev)

- Service `searxng` — profile `[serp]`, image `searxng/searxng:2026.8.1-8892414dc`.
- Mounts `./searxng/settings.yml`, loopback port `YANKI_SEARXNG_PORT` (default 8144).
- `mem_limit: 512m`.

### 5.2 `deploy/docker-compose.prod.yml`

- Same `searxng` service; no published port (internal `http://searxng:8080` only).
- Resource caps documented alongside worker/api.

### 5.3 `deploy/searxng/`

| File | Role |
|------|------|
| `settings.example.yml` | Tracked template (secret_key, JSON format, engine list) |
| `settings.yml` | **Gitignored** — operator copies from example |

### 5.4 `README.md`, `docs/operator-expected.md`, `docs/design.md`

- ADR-28 (SERP visibility), ADR-29 (compose profile).
- Operator checklist B6: stand up SearXNG, enable JSON format, set env vars.

**DataForSEO target:** remove container dependency; document API credentials instead.

---

## 6. API & frontend (consumers — no direct SearXNG)

### 6.1 Backend API

- `GET /api/v1/analyses/{id}/serp` — reads persisted `serp_checks` + summary (`routes.py`, `analysis_slices.py`).
- OpenAPI: `shared/contracts/openapi.json` — `serp_score`, `serp_status` on analysis bundle.

### 6.2 Frontend

| File | Role |
|------|------|
| `frontend/components/SerpVisibility.tsx` | Renders SERP score + check list |
| `frontend/app/analyses/[id]/page.tsx` | Analysis detail |
| `frontend/app/checker/[id]/page.tsx` | Checker results |
| `frontend/app/search-visibility/OverviewClient.tsx` | Search visibility overview |
| `frontend/lib/analysis-bundle.ts`, `api.ts`, `types.ts` | Types + fetch |
| `frontend/components/keywords/KeywordsChrome.tsx` | Keyword preview UI |
| Tests: `SerpVisibility*.test.tsx`, `checker.results.test.tsx`, etc. | Mock API responses |

**No browser → SearXNG calls.** All SERP data is server-side.

---

## 7. Tests & CI

### 7.1 Unit tests

| File | What it tests |
|------|----------------|
| `backend/tests/serp/test_searxng.py` | SearxngSource parsing (mock HTTP) |
| `backend/tests/serp/test_registry.py` | Registry builds SearxngSource |
| `backend/tests/keyword/test_searxng_expand.py` | Expand from SERP titles |
| `backend/tests/pipeline/test_serp_visibility.py` | Pipeline scoring logic |
| `backend/tests/pipeline/test_runner.py` | SERP on/off, fail-open, rerun |

### 7.2 Integration tests (live SearXNG)

| File | Gate |
|------|------|
| `backend/tests/integration/test_searxng_live.py` | `SERP_TEST_BASE_URL` |
| `backend/tests/integration/searxng/settings.yml` | CI instance config |
| `backend/tests/integration/searxng/fixture_engine.py` | Deterministic fake engine |

### 7.3 CI workflow — `.github/workflows/serp.yml`

- **integration** — real SearXNG (pinned image), PR gate.
- **migration** — alembic up/down for `0007`.
- **stack** — full analysis with `SERP_ENABLED=1` via `serp_stack_check.py`.
- **upstream** (scheduled) — drift check against `searxng/searxng:latest`.

### 7.4 Scripts

- `.github/scripts/serp_stack_check.py` — end-to-end SERP assertion after compose run.

---

## 8. Documentation references (non-runtime)

These mention SearXNG but are not code paths:

- `docs/architecture.md`, `docs/architecture-target.md` — target state mentions licensed SERP vendor (M4/M6).
- `docs/keyword-preview-oss.md` — keyword preview design.
- `docs/sessions/2026-08-03-01.md` — ADR-28 implementation notes.
- `docs/backlog.md`, `docs/tech-debt.md` — ops context.

Update during `dfs-9` (deploy docs).

---

## 9. Explicitly NOT SearXNG

| Component | Notes |
|-----------|-------|
| **Tavily** | `providers/tavily.py` → measured GEO grounded search. Separate swap decision (`dfs-8`). |
| **Simulated GEO** | `pipeline/simulated.py` — no live search. DFS used offline for validation only. |
| **Backlink module** | `backlink/` — separate vendor (`backlink_vendor`), not SearXNG. |
| **Site audit** | Planned Chromium crawl — unrelated to SERP adapter. |
| **Google Ads metrics** | Optional keyword volume — not SearXNG. |

---

## 10. Recommended swap order (from this map)

1. **`dfs-2`** — DataForSEO API spike (organic SERP + keyword suggestions endpoints).
2. **`dfs-4`** — `app/serp/dataforseo.py` implementing `SerpSource`.
3. **`dfs-5`** — Registry toggle; keep SearXNG behind legacy flag during transition.
4. **`dfs-6`** — `SearxngKeywordSource` → DFS-backed keyword source (or generic wrapper).
5. **`dfs-7`** — Rank-check (reuses same `SerpSource`).
6. **`dfs-9`** — Deploy: drop `searxng` service, update env/docs.
7. **`dfs-10`** — Retire or gate SearXNG tests + CI workflow.

---

## 11. Grep verification command

Re-run when the swap progresses:

```bash
rg -i 'searxng|SearxngSource|searxng_expand' --glob '!docs/sessions/**' .
```

Goal: zero runtime imports of SearXNG in production path; tests/docs may retain legacy references until `dfs-10`.
