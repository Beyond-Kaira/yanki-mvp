# Keyword Research preview (open-source path)

**Status:** preview path shipped — demand-test window  
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

## Discovery cleanup policy (accepted)

**Status:** core cleanup **complete** (order, smart-skip, variant cap, related/PAA filters).  
Optional 2nd SearXNG pass remains **off / not built** until explicit approval.  
**Canvas:** `keyword-discovery-cleanup.canvas.tsx` (implementation checklist)  
**Out of scope here:** Google Ads volume / CPC (`keyword-ads-volume-roadmap.canvas.tsx`).

Goal: Magic lists should read like **real search ideas**, not template spam.
Template variants stay an honest filler with `source=variant` — never presented
as Semrush-style “related keywords.”

### Ordering (expand merge priority)

When assembling `KeywordExpandResult.ideas` (after dedupe / brand exclude):

1. `seed` — the user phrase (once, first)
2. `suggestion` — SearXNG suggestions
3. `paa` — short answers that look like keyword ideas
4. `related` — weak phrases mined from SERP titles
5. `variant` — local English templates (`best {seed}`, …) last, if enabled

**Shipped:** `searxng_expand.py` / mock merge in this order so `max_ideas` is not
spent on filler first.

### Variant policy

| Rule | Decision |
|------|----------|
| Keep `source=variant` label | Yes — UI/API honesty |
| Smart-skip bad grammar (`best best…`, seed already contains shape tokens) | **Shipped** in `variants.py` |
| Cap / kill via config (e.g. `KEYWORD_VARIANT_MAX`, `0` = off) | **Shipped** (default **3**) |
| Locale-specific EN shapes for TR/non-Latin | **Shipped** skip when seed has non-basic-Latin letters; full i18n packs later |
| Second SearXNG round-trip over top suggestions | Optional, default **off** — only with explicit approval |

### Related workstreams (do not conflate)

| Track | Job |
|-------|-----|
| Discovery cleanup (this policy) | Order, smart-skip, variant cap, related/PAA junk filters |
| Ads volume roadmap | Real monthly searches / CPC on the metrics seam |
| Rank-check | Already shipped; unchanged by this policy |


## UI honesty

- Any non-Keyword-Planner volume-like score → label **Estimated**.
- Difficulty from SERP heuristics → label **Estimated difficulty** (not “KD%”).
- Empty / SearXNG down → clear error, not fake rows.

## Success criteria for “was the DB worth it?”

After a short preview period (target: **2–4 weeks** of real use once
`KEYWORD_ENABLED=1` on a live path), decide:

- **A** — OSS + proxies enough for our users → defer licensed data.
- **B** — Users bounce without real volume → add Google Ads / wholesale metrics adapter.
- **C** — Still no case for owning our own keyword index (aligns with `feature-parity.md` M6: licensed data first).

**A and C can both be true.** C is about *owning* an index; B is the only
path that says “buy metrics now.” Do not treat Semrush parity as the decision.

### Smoke before opening the window

Run once locally (or on the target deploy) with **live SearXNG**, not mock:

1. `DRY_RUN=0`, `KEYWORD_ENABLED=1`, `SERP_BASE_URL` pointing at a healthy SearXNG.
2. Sign in → Search Visibility → **Keyword Overview**: expand a real seed; ideas + Estimated badges visible; empty/error if SearXNG is down (no fake rows).
3. **Keyword Magic**: same expand; select ≤10 phrases; enter your domain; **Check ranks** returns `#n` / `no` / `n/a` (not a crash).
4. Kill-switch: set `KEYWORD_ENABLED=0`, reload — Keywords routes/API return unavailable (404), shell entry should not look “live” if gated the same way.
5. Optional: `DRY_RUN=1` still expands via mock for CI only — do not use that path to judge idea quality.

Config knobs: `KEYWORD_MAX_IDEAS`, `KEYWORD_VARIANT_MAX` (default 3; `0` = no
templates), `KEYWORD_RANK_MAX_QUERIES` (see `deploy/.env.example`).

### What to watch (lightweight — no analytics product required)

Capture notes in the session / Linear / Slack; numbers can be rough.

| Signal | Leans toward | Notes |
|--------|--------------|-------|
| Users return to Keywords without asking for “real volume” | **A** | Discovery + rank useful enough |
| First complaint is “where is search volume / KD?” or table ignored after Estimated | **B** | Metrics adapter next |
| Keywords nav unused; SERP overview already enough | **A or C** | Low urgency; keep kill-switch OFF or defer polish |
| Demand for Strategy Builder / Gap / history before volume | not B yet | Those are non-goals here — park; don’t buy a DB for clustering |
| SearXNG flaky / too slow / junk ideas dominate | Product-lite ops first | Fix instance/engines or cache before buying data |

### After the window — Product-lite fork

Whatever A/B/C you pick, the next *engineering* step is one of:

1. **Product-lite (no volume):** keep discovery + rank; harden quotas/errors; optionally **hide or demote** estimated demand/difficulty so nobody confuses them with Semrush columns → then claim Product on discovery/rank rows only.
2. **B path:** Google Ads Keyword Planner (or wholesale) on the same `KeywordSource` seam; replace `volume_estimated` with real volume; keep Estimated only where still proxy.
3. **Stay Preview:** leave kill-switch OFF outside experiments; revisit after other Search Visibility work.

Engineering follow-ups live in [keyword-preview-to-product-engineering.md](keyword-preview-to-product-engineering.md).

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
| Related / long-tail idea volume (breadth) | [x] | [ ] | [ ] | Preview: SearXNG suggestions + thin related. **Cleanup:** suggestions-first merge order (shipped). Product: larger, stable lists (licensed or cached). Semrush: billions-scale index, match types (broad/phrase/exact/related). |
| Local template variants (`best {seed}` …) | [x] | [ ] | — | Preview filler only (`source=variant`). Last in merge order; smart-skip; `KEYWORD_VARIANT_MAX` default 3 (`0` = off). Not a Semrush feature to copy. |
| Questions / PAA-style ideas | [x] | [ ] | [ ] | Preview: question-shaped SearXNG answers (`looks_like_paa_idea`). Product: reliable question filter. Semrush: Questions report + filters. |
| Topic / subgroup sidebar | [ ] | [ ] | [ ] | Not started. Product: light clustering. Semrush: Magic left-rail groups. |
| Match-type controls | [ ] | [ ] | [ ] | Semrush Magic. Preview skip. |
| Deduped, filtered junk (URL/prose/brand) | [x] | [ ] | [ ] | Preview: normalize + related seed-token coverage + domain/prose drops. Product: stronger NLP/locale + brand prefill. |
| Exclude / include filters (volume, KD, intent, …) | [ ] | [ ] | [ ] | Needs real metrics first for Product; Semrush = full filter bar. |
| Send to list / Strategy Builder | [ ] | [ ] | [ ] | Preview: optional light save later. Product: persisted lists. Semrush: Strategy Builder + SERP clustering. |

### B. Metrics (Overview cards + table columns)

| Capability | Preview | Product | Semrush | Notes / transition |
|------------|:-------:|:-------:|:-------:|--------------------|
| Absolute monthly search volume | [ ] | [ ] | [ ] | Preview→Product: Google Ads / wholesale. Semrush: own calibrated volume DB + history. |
| Volume labeled Estimated / proxy | [x] | — | — | `volume_estimated` + `estimated_demand_score` in signals. Drop when real volume ships (Product). |
| Trend (12-month) | [ ] | [ ] | [ ] | Needs time series / Planner monthly buckets. |
| Keyword Difficulty (true KD%) | [ ] | [ ] | [ ] | Preview has `estimated_difficulty_score` (seed SERP), not KD%. Product: licensed KD or honest “competition”. Semrush: KD%. |
| Personal KD (PKD) for a domain | [ ] | [ ] | [ ] | Needs domain + stronger model/vendor. |
| CPC / paid competitive density | [ ] | [ ] | [ ] | Ads/Planner or vendor. |
| Intent classification | [x] | [ ] | [ ] | Preview: rule markers in `intent.py`. Product: validated accuracy. Semrush: multi-intent labels at scale. |
| SERP features per keyword | [ ] | [ ] | [ ] | Partial via SearXNG page shape later; Semrush = feature inventory. |
| Global vs national vs local volume | [ ] | [ ] | [ ] | Locale pin ≠ local metrics today. |

### C. Overview (single-keyword snapshot)

| Capability | Preview | Product | Semrush | Notes / transition |
|------------|:-------:|:-------:|:-------:|--------------------|
| One-keyword metric cards | [x] | [ ] | [ ] | Preview Overview at `/search-visibility/keywords`. |
| Organic SERP top domains widget | [ ] | [ ] | [ ] | Can reuse live SERP; Product needs consistent engines/geo. |
| Paid / PLA copies | [ ] | [ ] | [ ] | Out of preview; Semrush Advertising adjacency. |
| Bulk analysis (many keywords) | [ ] | [ ] | [ ] | Product after metrics source; Semrush Bulk tab. |
| Historical metrics selector | [ ] | [ ] | [ ] | Semrush Guru+ territory; not preview. |

### D. Rank / visibility bridge (Yanki-native)

| Capability | Preview | Product | Semrush | Notes / transition |
|------------|:-------:|:-------:|:-------:|--------------------|
| On-demand “do we rank?” for selected queries | [x] | [ ] | [ ] | Preview: `POST /rank-check` + Magic UI; own-domain/subdomain only (`KEYWORD_RANK_MAX_QUERIES`). Product: trusted geo/engine. Semrush ≈ Position Tracking (different product). |
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
| Estimated / Preview badges in UI | [x] | — | — | Required while any proxy remains; remove per-field when Product-true. |
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

### Already in code

| Area | What we did on purpose | Why | Later fix (toward Product) |
|------|------------------------|-----|----------------------------|
| **Seed → template variants** (`build_seed_query_variants`) | Fixed English shapes; suggestions-first merge; smart-skip; capped by `KEYWORD_VARIANT_MAX` (default 3) | Zero-cost list filler | Locale template packs; or keep `0` forever. Never market as related. |
| **Single SearXNG round-trip per expand** | One `search(seed)` only — no fan-out over every variant | Politeness + latency on operator-hosted SearXNG | Optional budgeted second pass on top N suggestions; cache by `(seed, locale)` |
| **“Related” from SERP titles** | Title lines with whole-token seed coverage; drop prose/URL/long headlines | No related-keyword index in OSS | Higher NLP / drop “related” until a better signal exists |
| **PAA / answers** | Question-shaped short lines only (`looks_like_paa_idea` + EN `_QUESTION_PREFIXES`) | SearXNG `answers` inconsistent; EN markers = intentional Preview debt | Locale question packs; or soften to `?`/length-only |
| **Brand exclusion** | Optional `exclude_brands` + `leaks_brand` keys — caller must pass names | Expand is analysis-independent; no KYC on the request yet | Prefill from workspace domain / last analysis KYC when API exists |
| **No absolute volume / true KD** | Omitted as ground truth; **Estimated** proxies live in `signals` | No licensed DB yet | Google Ads Keyword Planner or wholesale API on the same `KeywordSource` seam; drop `volume_estimated` when real |
| **`estimated_demand_score`** | Provenance heuristic (suggestion > variant…) — **not** monthly searches | OSS demand-test ranking | Real `avgMonthlySearches`; keep score field or replace with `volume` |
| **`estimated_difficulty_score`** | Topic-level hint from **seed** SERP hard-host density (`difficulty_basis: seed_serp`) — **not** per-keyword KD% | One SearXNG round-trip budget | Per-keyword SERP or licensed KD; or keep forever as “competition hint” |
| **Intent (rules)** | Marker lists (`how` / `best` / `buy`…) | No model/vendor yet | Model-assisted or vendor intent; keep rules as fallback |
| **PAA question prefixes (EN)** | Hardcoded `_QUESTION_PREFIXES` in `normalize.py` | Same leak/i18n class as intent markers | Locale packs or drop question-word gate |
| **Mock under `DRY_RUN`** | Synthetic rows for CI | Same pattern as `MockSerpSource` | Keep forever for CI; never default in live preview |
| **Locale ≈ SearXNG `language`** | `locale` string mapped onto language pin | Good enough for preview; not full geo (gl/hl/city) | Proper country/geo params when SearXNG/engines support them; document mismatch in UI |
| **Overview vs Magic** | Thin Overview cards wrapping the same expand | Richer SERP snapshot per keyword only when budget allows |
| **Rank-check** | Own-domain/subdomain only via `rank_check.py` + Magic UI (`KEYWORD_RANK_MAX_QUERIES`, default 10); no brand/snippet text hits | Persistent rank tracking / history = separate M6 product, not this preview |
| **Estimated / Preview badges in UI** | Required while proxies remain | Remove per-field when Product-true metrics land |

### Still deferred (same honesty bar)

| Area | Planned intentional shortcut | Later fix (toward Product) |
|------|------------------------------|----------------------------|
| **UI lists / Strategy Builder** | Deferred or very light “save list” | Clustering only after demand proves keyword research retention |

### Doc / process notes

- Any new proxy metric ships with **Estimated** (or equivalent) in the UI copy and API (`volume_estimated: true` style flags where relevant).
- Matrix ticks and this roughness table must stay in sync when quality jumps.
- Primary decision after the preview window remains A / B / C under **Success criteria** — Semrush parity is optional, not the default north star.

## Debt notes (topla sonra — şimdilik işaret)

Parked for a cleanup pass after the preview path ships. Do not treat as done.

### Intent classifier — hardcoded markers (**leak / i18n risk**)

- **Where:** `backend/app/keyword/intent.py` — `_TRANSACTIONAL_MARKERS`, `_COMMERCIAL_MARKERS`, `_INFORMATIONAL_MARKERS`.
- **Behavior:** `classify_keyword_search_intent` returns the first matching bucket; **fallback is always `informational`** (including empty input).
- **Why it is debt:** English-only token lists; easy to reverse-engineer from UI labels (“our intent model”); wrong on TR/other locales; over-tags bland head terms as informational.
- **Product bar:** do not claim Product-grade intent until markers are replaced or heavily gated (locale packs, vendor/model, or “unclassified” instead of silent informational fallback).
- **Follow-up home:** [keyword-preview-to-product-engineering.md](keyword-preview-to-product-engineering.md) (engineering checklist Preview → Product).

### PAA question prefixes — hardcoded markers (**same class**)

- **Where:** `backend/app/keyword/normalize.py` — `_QUESTION_PREFIXES` used by `looks_like_paa_idea`.
- **Behavior:** answer must start with an EN question word (or end with `?`) to become a `paa` row.
- **Why it is debt:** English-only; TR/other locales under-keep real questions; list is reverse-engineerable.
- **Product bar:** locale packs, soften to length/`?` only, or stop claiming question quality.

### Other parked items (same cleanup pass)

- Seed template EN shapes — controlled (order + smart-skip + max); i18n packs still later.
- `estimated_*` proxies vs real volume/KD field swap (Ads roadmap).
- Optional 2nd SearXNG suggestion pass — not built; needs explicit approval + budget.
- Canvas vs this markdown tick sync for Product/Business.

## Related docs

| Doc | Audience |
|-----|----------|
| This file | Product + eng: preview scope, quality bars, roughness, demand-test, discovery cleanup policy |
| [keyword-preview-to-product-engineering.md](keyword-preview-to-product-engineering.md) | Engineers: codebase steps to lift Preview → Product |
| Cursor canvas `keyword-research-quality.canvas.tsx` | Product/Business progress board |
| Cursor canvas `keyword-discovery-cleanup.canvas.tsx` | Filler / keşif temizliği faz planı |
| Cursor canvas `keyword-ads-volume-roadmap.canvas.tsx` | Google Ads volume yolu (ayrı) |
