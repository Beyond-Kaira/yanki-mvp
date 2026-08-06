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

## Quality bars (how to read the matrices)

**Stakeholder view:** Product/Business can track progress on the Cursor canvas
`keyword-research-quality.canvas.tsx` (open beside chat in this workspace’s
canvases folder). This markdown stays the engineering source of truth — tick the
canvas in reviews, then mirror `[x]` here in the same PR.

Three bars — tick left-to-right as the capability matures. A capability can be
**shipped at Preview** while Product/Semrush stay unticked.

| Bar | Meaning | Honesty rule |
|-----|---------|--------------|
| **Preview** | Enough to test UX + learning (“is keyword research worth investing in?”). OSS / heuristics OK. | Must say Estimated / Preview where not ground truth. |
| **Product** | Yanki users can rely on it for real weekly work without feeling tricked. Licensed or first-party metrics OK; not full Semrush breadth. | Fake Semrush labels (e.g. “KD%”) only if methodology is ours and documented. |
| **Semrush** | Competitive parity with Semrush Keyword Analytics for that capability (depth, freshness, scale, secondary surfaces). | Usually needs licensed index + history + polish; not a near-term goal for every row. |

**How to use:** when a PR lifts quality, tick the new bar and note the transition in the same PR. Do not tick Semrush because “it looks similar in the UI.”

Legend in tables: `[x]` = met today (or committed for current preview path) · `[ ]` = not met · `—` = out of scope / N/A at that bar by choice.

---

## Capability matrix — Preview → Product → Semrush

Tick columns independently. Rows are everything that is **not** Semrush-quality
until its Semrush column is `[x]`.

### A. Discovery (Magic-style expand)

| Capability | Preview | Product | Semrush | Notes / transition |
|------------|:-------:|:-------:|:-------:|--------------------|
| Seed + locale expand entry point | [x] | [ ] | [ ] | Product: stable API + auth + rate limits + empty/error UX. Semrush: instant DB lookup, no live scrape dependency. |
| Related / long-tail idea volume (breadth) | [x] | [ ] | [ ] | Preview: SearXNG suggestions + thin related. Product: larger, stable lists (licensed or cached). Semrush: billions-scale index, match types (broad/phrase/exact/related). |
| Local template variants (`best {seed}` …) | [x] | [ ] | — | Preview only as filler. Product: either remove or smart-skip bad grammar; not a Semrush feature to copy. |
| Questions / PAA-style ideas | [x] | [ ] | [ ] | Preview: SearXNG answers heuristic. Product: reliable question filter. Semrush: Questions report + filters. |
| Topic / subgroup sidebar | [ ] | [ ] | [ ] | Not started. Product: light clustering. Semrush: Magic left-rail groups. |
| Match-type controls | [ ] | [ ] | [ ] | Semrush Magic. Preview skip. |
| Deduped, filtered junk (URL/prose/brand) | [x] | [ ] | [ ] | Preview: basic normalize. Product: stronger NLP/locale rules + workspace brand prefill. |
| Exclude / include filters (volume, KD, intent, …) | [ ] | [ ] | [ ] | Needs real metrics first for Product; Semrush = full filter bar. |
| Send to list / Strategy Builder | [ ] | [ ] | [ ] | Preview: optional light save later. Product: persisted lists. Semrush: Strategy Builder + SERP clustering. |

### B. Metrics (Overview cards + table columns)

| Capability | Preview | Product | Semrush | Notes / transition |
|------------|:-------:|:-------:|:-------:|--------------------|
| Absolute monthly search volume | [ ] | [ ] | [ ] | Preview→Product: Google Ads / wholesale. Semrush: own calibrated volume DB + history. |
| Volume labeled Estimated / proxy | [ ] | — | — | Faz 3 plan: Preview only. Drop when real volume ships (Product). |
| Trend (12-month) | [ ] | [ ] | [ ] | Needs time series / Planner monthly buckets. |
| Keyword Difficulty (true KD%) | [ ] | [ ] | [ ] | Preview: difficulty_proxy only. Product: licensed KD or honest “competition”. Semrush: KD%. |
| Personal KD (PKD) for a domain | [ ] | [ ] | [ ] | Needs domain + stronger model/vendor. |
| CPC / paid competitive density | [ ] | [ ] | [ ] | Ads/Planner or vendor. |
| Intent classification | [ ] | [ ] | [ ] | Preview: rules (Faz 3). Product: validated accuracy. Semrush: multi-intent labels at scale. |
| SERP features per keyword | [ ] | [ ] | [ ] | Partial via SearXNG page shape later; Semrush = feature inventory. |
| Global vs national vs local volume | [ ] | [ ] | [ ] | Locale pin ≠ local metrics today. |

### C. Overview (single-keyword snapshot)

| Capability | Preview | Product | Semrush | Notes / transition |
|------------|:-------:|:-------:|:-------:|--------------------|
| One-keyword metric cards | [ ] | [ ] | [ ] | Planned thin Overview on same expand. |
| Organic SERP top domains widget | [ ] | [ ] | [ ] | Can reuse live SERP; Product needs consistent engines/geo. |
| Paid / PLA copies | [ ] | [ ] | [ ] | Out of preview; Semrush Advertising adjacency. |
| Bulk analysis (many keywords) | [ ] | [ ] | [ ] | Product after metrics source; Semrush Bulk tab. |
| Historical metrics selector | [ ] | [ ] | [ ] | Semrush Guru+ territory; not preview. |

### D. Rank / visibility bridge (Yanki-native)

| Capability | Preview | Product | Semrush | Notes / transition |
|------------|:-------:|:-------:|:-------:|--------------------|
| On-demand “do we rank?” for selected queries | [ ] | [ ] | [ ] | Faz 6 plan: SearXNG + `detect`. Product: trusted geo/engine. Semrush ≈ Position Tracking (different product). |
| Existing analysis SERP visibility (~6 topic queries) | [x] | [ ] | — | Already live on Search Visibility overview — complementary, not Magic. |
| Persistent rank tracking + history | [ ] | [ ] | [ ] | Explicit non-goal for this preview; M6. Semrush Position Tracking parity. |

### E. Strategy / organization

| Capability | Preview | Product | Semrush | Notes / transition |
|------------|:-------:|:-------:|:-------:|--------------------|
| Saved keyword lists | [ ] | [ ] | [ ] | Light save optional in preview. |
| SERP-based clustering / pillar pages | [ ] | [ ] | [ ] | Semrush Strategy Builder. |
| Keyword Gap (you vs competitors) | [ ] | [ ] | [ ] | Non-goal for preview. |
| Export CSV / reporting blocks | [ ] | [ ] | [ ] | Product hygiene; Semrush exports + reports. |

### F. Platform / trust

| Capability | Preview | Product | Semrush | Notes / transition |
|------------|:-------:|:-------:|:-------:|--------------------|
| Kill-switch + config (`KEYWORD_ENABLED`) | [x] | [ ] | — | Product: ops runbooks, quotas per org. |
| Estimated / Preview badges in UI | [ ] | — | — | Required while any proxy remains; remove per-field when Product-true. |
| `KeywordSource` seam (swap vendor without UI rewrite) | [x] | [x] | [ ] | Product bar met when live SearXNG (+ later Ads) plug in; Semrush would be irrelevant if we never own their DB. |
| Cost / rate limits / caching | [ ] | [ ] | [ ] | Product must not melt SearXNG; Semrush = their infra. |
| Multi-country databases, freshness SLA | [ ] | [ ] | [ ] | Semrush-scale ops. |

---

## Transition cheatsheet (Preview → Product → Semrush)

Use this when prioritizing. Each arrow is a **decision**, not automatic polish.

| Jump | Typical unlock | Stop condition |
|------|----------------|----------------|
| **Preview → Product** | Users keep using Magic without complaining about fake numbers; add real volume (or drop volume column); harden filters, geo, auth, quotas; remove Estimated where data is real | Still learning / A-path: stay on Preview and keep badges |
| **Product → Semrush** | Licensed breadth (related at scale, KD, intent, SERP features, history) + UX parity (match types, clusters, gap, bulk) | Usually **not** required for Yanki’s wedge — prefer “good Product” over fake Semrush unless competitive sales demand it |
| **Skip Semrush** | Valid: ship Product metrics + Yanki rank/AI bridges; leave Strategy Builder / Gap / 27B index unticked forever | Document as `—` under Semrush so nobody “almost Semrush”s the UI |

**Current stance (this doc’s A/B/C):** Preview first → learn → either stay Preview-good, buy Product metrics (B), or still avoid owning an index (C). Semrush column is a **map**, not a commitment.

---

## Intentional roughness (detail — why Preview ticks are “rough”)

These are **conscious** shortcuts for the OSS demand-test — not forgotten TODOs.
When a matrix row moves Preview → Product, update both the matrix tick **and**
the matching row here (or delete it) in the same PR.

### Already in code (Faz 0–2)

| Area | What we did on purpose | Why | Later fix (toward Product) |
|------|------------------------|-----|----------------------------|
| **Seed → template variants** (`build_seed_query_variants`) | Paste user seed into fixed English shapes (`best {seed}`, `{seed} reviews`, …) with no grammar / language check | Zero-cost list filler; mirrors `serp_visibility` query shapes; real ideas should mainly come from SearXNG suggestions | Skip shapes if seed already starts with that word (`best best…`); locale-specific templates; disable variants for tiny/huge/non-Latin seeds; prefer suggestions-first ordering in the UI |
| **Single SearXNG round-trip per expand** | One `search(seed)` only — no fan-out over every variant | Politeness + latency on operator-hosted SearXNG | Optional budgeted second pass on top N suggestions; cache by `(seed, locale)` |
| **“Related” from SERP titles** | Title lines that contain the seed, stripped at `—` / `\|` | No related-keyword index exists in OSS | Drop titles that look like brands/URLs; require higher token overlap; or drop “related” until a better signal exists |
| **PAA / answers** | Keep short lines; drop prose ending in `.` / long blobs | SearXNG `answers` shape is inconsistent across engines | Engine-aware parsing; question-only filter (`who/what/how…`) |
| **Brand exclusion** | Optional `exclude_brands` + `leaks_brand` keys — caller must pass names | Expand is analysis-independent; no KYC on the request yet | Prefill from workspace domain / last analysis KYC when API exists |
| **No volume / true KD** | Omitted; proxies planned in Faz 3 as **Estimated** only | No licensed DB yet | Google Ads Keyword Planner or wholesale API on the same `KeywordSource` seam |
| **Mock under `DRY_RUN`** | Synthetic rows for CI | Same pattern as `MockSerpSource` | Keep forever for CI; never default in live preview |
| **Locale ≈ SearXNG `language`** | `locale` string mapped onto language pin | Good enough for preview; not full geo (gl/hl/city) | Proper country/geo params when SearXNG/engines support them; document mismatch in UI |

### Planned rough edges (Faz 3+ — not built yet, same honesty bar)

| Area | Planned intentional shortcut | Later fix (toward Product) |
|------|------------------------------|----------------------------|
| **`demand_proxy`** | Heuristic from how the idea was found (suggestion vs local variant, etc.) — **not** monthly searches | Real `avgMonthlySearches` via Google Ads / wholesale; keep field name stable, swap provider |
| **`difficulty_proxy`** | Heuristic from SERP composition (big-brand density, etc.) — **not** Semrush KD% | Licensed KD or clearer label forever as “competition hint” |
| **Intent** | Rule keywords (`how` → informational, `best`/`vs` → commercial, …) | Model-assisted or vendor intent; keep rules as fallback |
| **Overview vs Magic** | Thin Overview cards wrapping the same expand | Richer SERP snapshot per keyword only when budget allows |
| **Rank-check** | Reuse `detect` on a small selected set (budget 6–10) | Persistent rank tracking / history = separate M6 product, not this preview |
| **UI lists / Strategy Builder** | Deferred or very light “save list” | Clustering only after demand proves keyword research retention |

### Doc / process notes

- Any new proxy metric ships with **Estimated** (or equivalent) in the UI copy and API (`volume_estimated: true` style flags where relevant).
- Matrix ticks and this roughness table must stay in sync when quality jumps.
- Primary decision after the preview window remains A / B / C under **Success criteria** — Semrush parity is optional, not the default north star.
