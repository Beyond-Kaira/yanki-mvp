# Yanki — Google Ads API access overview

**Status:** Research / internal prototype (not commercially launched)  
**Date:** 2026-08-10  
**Company / product:** Yanki (test deployment: https://yanki.beyondkaira.com)  
**Google Ads manager (MCC) ID:** 7825138733  
**Google Cloud project number:** 464395157673

## 1. What we are building

Yanki is an early-stage B2B prototype for search and AI visibility research, including a **Keyword Research** screen. A user (today: only our developers) enters a seed keyword; the product expands related keyword ideas and displays research signals.

This is **not** a live commercial product. There are no paying customers, no revenue, and no external client deployments. The URL above is our **test / staging** environment and is used only by our engineering and product team for experimentation.

## 2. Why we need the Google Ads API

We need **Basic Access** so we can call Keyword Planning historical metrics in research:

- **Service / method:** `KeywordPlanIdeaService.GenerateKeywordHistoricalMetrics`
- **Data used:** historical average monthly searches, competition, and top-of-page bid ranges (when available)
- **Purpose:** evaluate whether showing real search volume next to keyword ideas is useful inside Yanki’s Keyword Research prototype

We do **not** use the Google Ads API to:

- create, edit, or optimize Google Ads campaigns, ad groups, ads, or budgets
- manage accounts for external advertisers
- resell or redistribute raw Google Ads API data as a standalone dataset

## 3. Intended audience (current vs later)

| Now (research phase) | Later (if productized) |
|----------------------|-------------------------|
| Internal developers / product only | Marketers, SEO practitioners, and agencies using Yanki as B2B SaaS |

Even in a later product stage, intended API use would remain **keyword metrics display inside Yanki**, not campaign management.

## 4. Architecture (high level)

1. User enters a seed keyword in Yanki Keyword Research (test env).
2. Yanki expands keyword ideas via our discovery path (separate from Google Ads).
3. When Ads metrics are enabled, Yanki batches those phrases and calls `GenerateKeywordHistoricalMetrics`.
4. Returned volume / competition fields are shown in the UI as research metrics.
5. If Ads is unavailable, the UI does not invent fake Ads volume; discovery can still run with estimated proxies clearly labeled.

Credentials (developer token, OAuth client, refresh token, customer IDs) stay in private deployment config and are never committed to source control.

## 5. Compliance notes for review

- **Access requested:** Basic Access  
- **Permissible use needed:** researching keywords (Keyword Planning / KeywordPlanIdeaService)  
- **Environment:** research prototype; developer-only usage today  
- **Primary website:** https://yanki.beyondkaira.com (test URL)

---

Contact for this application: the API Contact Email configured in the Google Ads API Center for MCC `7825138733`.
