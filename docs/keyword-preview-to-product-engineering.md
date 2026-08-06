# Keyword preview → Product (engineering checklist)

**Audience:** engineers  
**Status:** stub — fill in at end of preview implementation day / cleanup pass  
**Companion:** [keyword-preview-oss.md](keyword-preview-oss.md) (scope, quality bars, intentional roughness)

This doc is the **codebase-shaped** path from Preview quality to Product quality.
Product/Business track *what* on the quality canvas; this track *where in the
repo* and *what to change*.

## How to use

1. Keep Preview honest (Estimated badges, no fake KD%).
2. For each capability you want at Product, add a section below with:
   - current Preview files
   - Product acceptance criteria
   - concrete code/config changes
   - tests / flags
3. Tick the quality matrix in `keyword-preview-oss.md` + canvas in the same PR.

## Parked debt (must address before claiming Product intent)

| Debt | Location | Risk | Product direction |
|------|----------|------|-------------------|
| Hardcoded EN intent markers | `backend/app/keyword/intent.py` | **Leak / reverse-engineering**; i18n wrong; silent `informational` fallback over-tags | Locale packs, vendor/model intent, or return `unclassified` instead of defaulting to informational |
| Seed template variants | `backend/app/keyword/variants.py` | Bad grammar (`best best…`) | Smart-skip / disable / suggestions-first UI |
| Demand ≠ volume | `backend/app/keyword/signals.py` | Users read score as volume | Ads/wholesale `volume` field; drop `volume_estimated` when real |
| Difficulty = seed SERP only | `signals.py` + one SearXNG page | Not per-keyword KD | Per-query SERP budget or licensed KD; keep label “competition hint” if not |

## Preview → Product workstreams (fill as phases land)

### A. Discovery expand

- **Preview now:** `keyword/searxng_expand.py`, `normalize.py`, `variants.py`
- **Product next:** _(TBD — API auth, caching, brand prefill from KYC)_

### B. Metrics

- **Preview now:** `intent.py`, `signals.py` (estimated only)
- **Product next:** _(TBD — Google Ads / wholesale adapter on `KeywordSource`)_

### C. HTTP + UI

- **Preview now:** `POST /api/v1/keywords/expand` + `/overview` (`keyword_routes.py`); 404 when `KEYWORD_ENABLED=0`; auth required; `estimated: true` on responses
- **Product next:** org quotas, stronger rate limits, OpenAPI-driven frontend types (`make gen-types`), Estimated badges in UI (Faz 5)

### D. Rank bridge

- **Preview now:** analysis SERP visibility only
- **Product next:** _(TBD — `rank-check` + `serp_visibility.detect`)_

## Open questions for the cleanup pass

- Is silent `informational` fallback acceptable in Product, or must unknown be `unclassified`?
- Ship Product-lite without volume (discovery + rank only) vs require Ads volume for Product bar on metrics?
