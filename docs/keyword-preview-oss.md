# Keyword Research preview (open-source path)

**Status:** accepted for implementation  
**Goal:** Learn whether a licensed keyword database is worth buying — by shipping a usable Search Visibility → Keywords preview **without** owning a Semrush-scale index.

## Product promise

Users can:

1. Enter a **seed** phrase and a **locale** (country).
2. Get a list of related search ideas (Magic-style table).
3. See **estimated** demand / difficulty signals (clearly labeled).
4. Optionally check whether **their domain** appears for selected queries (reuse live SERP).

This is **not** Semrush Keyword Overview/Magic parity. Exact search volume, true KD/PKD, CPC, and a global keyword index are out of scope until a later licensed adapter.

## Data sources

| Need | Preview source | Not using |
|------|----------------|-----------|
| Idea expansion (related / suggestions / PAA / query variants) | **SearXNG** (already in stack via `SerpSource`) | Paid keyword DB |
| Rank / “did we appear?” | **SearXNG** + existing hit detection (`serp_visibility.detect`) | — |
| Absolute monthly volume | Deferred (Google Ads Keyword Planner API or wholesale API) | Invented numbers presented as fact |
| True keyword difficulty | Deferred; **proxy** from SERP composition only | Semrush KD |

**Mock** (`MockKeywordSource`) is only for `DRY_RUN` / CI when SearXNG is unavailable. Normal local and deployed preview must call SearXNG. Do not build the UI against mock as the default path.

## Architecture

Mirror `SerpSource`:

- New package: `backend/app/keyword/` with a `KeywordSource` protocol.
- Registry: live → SearXNG-backed expander; `DRY_RUN` → mock.
- HTTP: `POST /api/v1/keywords/expand`, `overview`, `rank-check` — **not** tied to `analysis_id` (unlike AI Visibility tabs).
- Kill-switch: `KEYWORD_ENABLED` (same idea as `CHECKER_ENABLED` / `SERP_ENABLED`).
- UI: `/search-visibility/keywords` (+ Magic), shell-nav entry under Search Visibility; show an **Estimated / preview** badge wherever metrics are proxies.

Later volume vendors plug into the same `KeywordSource` seam; UI stays stable.

## UI honesty

- Any non-Keyword-Planner volume-like score → label **Estimated**.
- Difficulty from SERP heuristics → label **Estimated difficulty** (not “KD%”).
- Empty / SearXNG down → clear error, not fake rows.

## Success criteria for “was the DB worth it?”

After a short preview period, decide:

- **A** — OSS + proxies enough for our users → defer licensed data.
- **B** — Users bounce without real volume → add Google Ads / wholesale metrics adapter.
- **C** — Still no case for owning our own keyword index (aligns with `feature-parity.md` M6: licensed data first).

## Explicit non-goals (this preview)

- Building or crawling a proprietary keyword database.
- Keyword Strategy Builder clustering.
- Keyword Gap.
- Historical rank tracking time-series (separate M6 track).
