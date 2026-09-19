# DataForSEO touchpoint map

**Status:** Active — Phase A (mod-2 supplement)  
**Scope:** Where DataForSEO replaces or augments current search/backlink vendors when feature branches merge.

Parent: [module-coupling-map.md](./module-coupling-map.md) · Plan: [standalone-modules-plan.md](./standalone-modules-plan.md)

---

## Billing boundaries

DataForSEO products are **separate credit pools**:

| Product | Used for | Typical env / registry |
|---------|----------|------------------------|
| **Organic SERP API** | Ranked results, PAA, related searches | `SERP_PROVIDER=dataforseo`, `app/serp/dataforseo.py` |
| **Keywords Data API** | Search volume, keyword suggestions | `KEYWORD_ADS_ENABLED=1`, `app/keyword/metrics/dataforseo.py` |
| **Backlinks API** | Referring domains, summary, history | `BACKLINK_VENDOR=dataforseo`, `app/backlink/dataforseo.py` (planned) |

A 402 on one product does not necessarily mean all are exhausted.

---

## Touchpoints by module

### SERP visibility

| Area | File(s) | Today (main) | Target (feat/dataforseo-serp-adapter) |
|------|---------|--------------|--------------------------------------|
| Adapter | `app/serp/dataforseo.py` | — | `SerpSource` implementation |
| Registry | `app/serp/registry.py` | `searxng` + `mock` | `dataforseo` when `SERP_PROVIDER=dataforseo` |
| Pipeline | `app/pipeline/serp_visibility.py` | Called from footprint step | Same; later also standalone `serp_run` (mod-3) |
| Storage | `serp_checks`, `analyses.serp_*` | SearXNG source name | `source=dataforseo` |
| Deploy | `deploy/docker-compose.yml` | SearXNG service optional | `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD` (dfs-9) |

### Keywords

| Area | File(s) | Today (main) | Target (feat/dataforseo-keyword-expand) |
|------|---------|--------------|------------------------------------------|
| Expand | `app/keyword/searxng_expand.py` → dataforseo | SearXNG HTML parse | DataForSEO SERP suggestions |
| Rank check | `app/keyword/rank_check.py` | SearXNG organic positions | DataForSEO SERP positions |
| Volume | `app/keyword/metrics/google_ads.py` | Direct Google Ads API | `app/keyword/metrics/dataforseo.py` |
| Registry | `app/keyword/registry.py`, `metrics/registry.py` | SearXNG + Google Ads | Shared `SERP_PROVIDER` + DataForSEO volume |
| API | `app/api/keyword_routes.py` | `/keywords/expand`, `/rank-check` | Unchanged surface |

### Backlinks (not started on main)

| Area | File(s) | Today | Target (b0–b5, mod-10) |
|------|---------|-------|------------------------|
| Adapter | `app/backlink/mock.py` | Deterministic mock index | `app/backlink/dataforseo.py` |
| Registry | `app/backlink/registry.py` | `mock` only | `BACKLINK_VENDOR=dataforseo` |
| Refresh | `app/api/backlink_routes.py` | Project-scoped refresh | Same contract, real vendor |
| Gap / unlinked | `app/backlink/gap.py` | Reads geo + serp rows | mod-7 explicit run ids |

### Not using DataForSEO

| Module | Reason |
|--------|--------|
| AI Visibility (GEO) | LLM + optional Tavily; no DFS GEO product |
| KYC / BrandContext | Own crawl + OpenRouter extraction |
| Site audit | Own Chromium crawl |
| Checker | Uses GEO pipeline subset |

---

## Migration tasks (dfs-* ↔ mod-*)

| Task | Relationship |
|------|--------------|
| dfs-1 … dfs-7 | SERP + keyword swap — enables mod-3 live smoke |
| dfs-9, dfs-10 | Deploy cleanup — remove SearXNG dependency |
| k0 … k8 | Keyword PR track — volume, rank-check, expand |
| b0 … b5 | Backlinks PR track — mod-10 implementation |
| mod-3 | Standalone SERP runs — consumes merged SERP adapter |
| mod-10 | Backlinks adapter in standalone refresh path |

---

## Validation corpus (val-sh-3)

Linkage validation pulls DataForSEO SERP snapshots for frozen prompt texts. Depends on SERP adapter merge + credits, not on standalone module APIs.
