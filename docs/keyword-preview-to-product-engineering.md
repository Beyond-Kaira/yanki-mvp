# Keyword preview → Product (engineering checklist)

**Audience:** engineers  
**Status:** preview shipped; use after demand-test A/B/C (see companion)  
**Companion:** [keyword-preview-oss.md](keyword-preview-oss.md) (scope, quality bars, intentional roughness, demand-test)

This doc is the **codebase-shaped** path from Preview quality to Product quality.
Product/Business track *what* on the quality canvas; this track *where in the
repo* and *what to change*.

## How to use

1. Keep Preview honest (Estimated badges, no fake KD%).
2. Run the demand-test window in the companion doc before claiming Product on metrics.
3. For each capability you want at Product, add a section below with:
   - current Preview files
   - Product acceptance criteria
   - concrete code/config changes
   - tests / flags
4. Tick the quality matrix in `keyword-preview-oss.md` + canvas in the same PR.

## Parked debt (must address before claiming Product intent)

| Debt | Location | Risk | Product direction |
|------|----------|------|-------------------|
| Hardcoded EN intent markers | `backend/app/keyword/intent.py` | **Leak / reverse-engineering**; i18n wrong; silent `informational` fallback over-tags | Locale packs, vendor/model intent, or return `unclassified` instead of defaulting to informational |
| Seed template variants | `backend/app/keyword/variants.py` | Bad grammar (`best best…`) | Smart-skip / disable / suggestions-first UI |
| Demand ≠ volume | `backend/app/keyword/signals.py` | Users read score as volume | Ads/wholesale `volume` field; drop `volume_estimated` when real — **or** hide scores in Product-lite |
| Difficulty = seed SERP only | `signals.py` + one SearXNG page | Not per-keyword KD | Per-query SERP budget or licensed KD; keep label “competition hint” if not |

## Preview → Product workstreams

### A. Discovery expand

- **Preview now:** `keyword/searxng_expand.py`, `normalize.py`, `variants.py`
- **Product next:** caching by `(seed, locale)`; brand prefill from workspace/KYC; stronger junk filters; org rate limits

### B. Metrics

- **Preview now:** `intent.py`, `signals.py` (estimated only)
- **Product next (pick one after demand-test):**
  - **B path:** Google Ads / wholesale adapter on `KeywordSource`; real `volume`; drop `volume_estimated`
  - **Product-lite:** remove or demote estimated demand/difficulty columns; do not tick Product on volume/KD rows

### C. HTTP + UI

- **Preview now:** `POST /api/v1/keywords/expand` + `/overview` + `/rank-check`; UI at `/search-visibility/keywords` (+ `/magic`); Estimated badge; shell-nav live
- **Product next:** org quotas, stronger rate limits, clearer SearXNG-down UX, volume column honesty when Ads lands

### D. Rank bridge

- **Preview now:** `POST /api/v1/keywords/rank-check` + Magic select/check; own-domain match only (`rank_check.py`); analysis SERP visibility still complementary
- **Product next:** trusted geo/engine, org quotas, clearer miss vs unmeasurable UX; persistent history remains M6 (out of this preview)

## Open questions for the cleanup pass

- Is silent `informational` fallback acceptable in Product, or must unknown be `unclassified`?
- After demand-test: Product-lite without volume (discovery + rank) vs require Ads volume for Product bar on metrics?
