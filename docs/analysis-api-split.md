# Analysis API read split

**Status:** phase 2 shipped — thin main GET + frontend slice polling.  
**Canvas:** `analysis-endpoint-split.canvas.tsx`

## Goal

Split the fat `GET /api/v1/analyses/{id}` envelope into feature slices so
Search Visibility and AI Visibility can poll only what they need.

## What stays the same

- `POST /api/v1/analyses` — one job, six worker steps (discovery → scoring).
- ADR-28 (SERP rides in footprint) and ADR-31 (SEO rides in discovery) — worker
  layout unchanged.
- Keywords (`/keywords/*`), Site Audit (`/seo-projects/*`), Backlinks — separate
  modules; out of scope.

## Main GET (phase 2)

`GET /analyses/{id}` returns a **thin poll envelope** — status, progress, error,
and summary columns (`geo_score`, `footprint_count`, SERP/SEO headlines). No
nested `result`.

Feature payloads live on slice routes (below). The frontend merges slices into
the legacy `Analysis` shape (`lib/analysis-bundle.ts`) so existing UI helpers
keep working.

## Slice routes

| Method | Path | Body | Notes |
|--------|------|------|--------|
| GET | `/analyses/{id}/kyc` | `{ "kyc": … \| null }` | Same as former `result.kyc` |
| GET | `/analyses/{id}/prompts` | `{ "prompts": […] }` | Deterministic set from KYC |
| GET | `/analyses/{id}/geo` | `GeoOut` | Responses, geo_records, scores, interventions |
| GET | `/analyses/{id}/serp` | `SerpVisibilityOut \| null` | Null = not measured |
| GET | `/analyses/{id}/seo` | `SeoAuditOut \| null` | Homepage audit only; null = not audited |

Auth matches `GET /analyses/{id}`: `readable_analysis` (capability URL for
org-less rows; org-scoped when `org_id` is set).

Implementation: `app/api/analysis_slices.py` builders; `build_envelope()` for the
main GET.

## Frontend polling (phase 2)

| Surface | Poll | Slices on terminal |
|---------|------|-------------------|
| Search Visibility | thin GET | `/serp` + `/seo` |
| AI Visibility | thin GET | `/geo` + `/kyc` + `/prompts` |
| Legacy `/analyses/[id]`, checker | thin GET | all slices (`full`) |

Hook: `useAnalysisQuery({ slices: 'search' | 'ai' | 'full' })`.

## Later PRs

- `PATCH /analyses/{id}/kyc` + prompt regen; profile/measure write split.
- Guided wizard UI (KYC review → prompts → measure).
- Optional DB: `kyc_profiles`, `analysis_feature_runs`.

## Tests

- `tests/test_analysis_slices.py` — slice builders + thin GET.
- `tests/test_cross_tenant_leakage.py` — new routes in `CAPABILITY` set.
- `frontend/tests/analysisMocks.ts` — poll + slice merge fixtures.
