# Analysis API read split (phase 1)

**Status:** phase 1 shipped — additive slice GETs; main GET unchanged.  
**Canvas:** `analysis-endpoint-split.canvas.tsx`

## Goal

Split the fat `GET /api/v1/analyses/{id}` envelope into feature slices so
Search Visibility and AI Visibility can poll only what they need. Phase 1 adds
new routes **without** changing the existing GET (frontend keeps working).

## What stays the same

- `POST /api/v1/analyses` — one job, six worker steps (discovery → scoring).
- `GET /api/v1/analyses/{id}` — full `result.*` blob (unchanged shape).
- ADR-28 (SERP rides in footprint) and ADR-31 (SEO rides in discovery) — worker
  layout unchanged in phase 1.
- Keywords (`/keywords/*`), Site Audit (`/seo-projects/*`), Backlinks — separate
  modules; out of scope.

## New routes (phase 1)

| Method | Path | Body | Notes |
|--------|------|------|--------|
| GET | `/analyses/{id}/kyc` | `{ "kyc": … \| null }` | Same as `result.kyc` |
| GET | `/analyses/{id}/prompts` | `{ "prompts": […] }` | Deterministic set from KYC |
| GET | `/analyses/{id}/geo` | `GeoOut` | Responses, geo_records, scores, interventions |
| GET | `/analyses/{id}/serp` | `SerpVisibilityOut \| null` | Null = not measured |
| GET | `/analyses/{id}/seo` | `SeoAuditOut \| null` | Homepage audit only; null = not audited |

Auth matches `GET /analyses/{id}`: `readable_analysis` (capability URL for
org-less rows; org-scoped when `org_id` is set).

Implementation: `app/api/analysis_slices.py` builders shared with `_to_out`.

## Phase 2 (later PRs)

- Thin `GET /analyses/{id}` (status + top-level scores only).
- Frontend slice polling (Search → `/serp` + `/seo`; AI → `/geo` + `/kyc`).
- `PATCH /analyses/{id}/kyc` + prompt regen; profile/measure write split.
- Optional DB: `kyc_profiles`, `analysis_feature_runs`.

## Tests

- `tests/test_analysis_slices.py` — slice parity with full GET.
- `tests/test_cross_tenant_leakage.py` — new routes in `CAPABILITY` set.
