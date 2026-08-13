# Keyword preview → Product (engineering checklist)

**Audience:** engineers  
**Status:** discovery cleanup core done; Ads volume policy accepted — implement after API access  
**Companion:** [keyword-preview-oss.md](keyword-preview-oss.md) (scope, quality bars, discovery + Ads policies)

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
| Hardcoded EN PAA question prefixes | `backend/app/keyword/normalize.py` (`_QUESTION_PREFIXES`) | Same leak / i18n class as intent markers; TR questions miss | Locale packs, `?`-only soften, or drop question gate |
| Demand ≠ volume | `backend/app/keyword/signals.py` | Users read score as volume | Ads/wholesale `volume` field; drop `volume_estimated` when real — **or** hide scores in Product-lite |
| Difficulty = seed SERP only | `signals.py` + one SearXNG page | Not per-keyword KD | Per-query SERP budget or licensed KD; keep label “competition hint” if not |

## Preview → Product workstreams

### A. Discovery expand

- **Preview now:** `keyword/searxng_expand.py`, `normalize.py`, `variants.py`
- **Accepted policy:** merge order `seed → suggestion → paa → related → variant`; variant capped (`KEYWORD_VARIANT_MAX`, default target 3); smart-skip; never sell variant as related. See companion **Discovery cleanup policy**.
- **Cleanup:** **core complete.** Optional budgeted 2nd SearXNG pass — only with explicit approval (not built).
- **Shipped in cleanup:** suggestions-first merge; smart-skip; `KEYWORD_VARIANT_MAX` (default 3); tighter related/PAA filters
- **Product next:** caching by `(seed, locale)`; brand prefill from workspace/KYC; stronger junk filters; org rate limits; optional 2nd SearXNG pass only with budget approval

### B. Metrics

- **Preview now:** `intent.py`, `signals.py` (estimated only)
- **Accepted path:** Google Ads Keyword Planning on a metrics seam (not replacing SearXNG discovery). See companion **Ads volume metrics policy**.
- **Next:** Google account + developer token smoke → `KEYWORD_ADS_ENABLED` adapter → expand/overview enrich + Volume UI → cache/QPS
- **Fallback (only if Ads blocked):** wholesale on the same seam; or Product-lite (hide estimated demand/difficulty)

### C. HTTP + UI

- **Preview now:** `POST /api/v1/keywords/expand` + `/overview` + `/rank-check`; UI at `/search-visibility/keywords` (+ `/magic`); Estimated badge; shell-nav live
- **Product next:** org quotas, stronger rate limits, clearer SearXNG-down UX, volume column honesty when Ads lands

### D. Rank bridge

- **Preview now:** `POST /api/v1/keywords/rank-check` + Magic select/check; own-domain match only (`rank_check.py`); analysis SERP visibility still complementary
- **Product next:** trusted geo/engine, org quotas, clearer miss vs unmeasurable UX; persistent history remains M6 (out of this preview)

## Open questions for the cleanup pass

- Is silent `informational` fallback acceptable in Product, or must unknown be `unclassified`?
- After demand-test: Product-lite without volume (discovery + rank) vs require Ads volume for Product bar on metrics?
