# Yanki — Competitive Feature Parity Analysis

> **Dated snapshot — read the banner before the table.** This parity analysis
> was taken 2026-08-05, and M1 stages A1–A4 plus the M2 backlink engine landed
> *after* it. The "Yanki today" column is therefore wrong in three families of
> rows: **organizations / seats / roles** are built (backend + Admin Panel UI),
> **audit logging** is emitted, queryable and tamper-evident rather than "not
> even emitted", and **backlinks** are an engine behind a flag rather than
> nothing — with no API router and no UI, so the customer-facing verdict of ✖
> still stands for that row. Everything else in the table was re-checked at
> session 22 close and holds. The parity *verdicts* are unchanged; only those
> current-state cells moved.


*Audience: founders, PM, engineering leads. This document is the canonical
answer to "what does the category consider table-stakes, and which of it does
Yanki have?" It drives the parity portion of the roadmap
([roadmap.md](roadmap.md), milestones M3–M6) and the prioritized feature
backlog. The strategy source is
[Yanki_Geo_Intelligence_Report.pdf](Yanki_Geo_Intelligence_Report.pdf) (the
planning baseline, Aug 2026); the "Yanki today" column is grounded in the
repository as inspected on **2026-08-05** (including the undocumented PR #11
measured/simulated pivot and PR #23 Site Audit — see tech-debt #54/#55).*

*Competitive claims are an **August 2026 snapshot** (the baseline report's own
caveat). Re-verify before external use.*

**Status: adopted planning baseline — 2026-08-05 (session 20, ADR-33).**

---

## 1. The competitor set

From the planning baseline (report §1), the platforms Yanki is measured
against, grouped the way the market actually buys:

| Ring | Players | What they anchor |
|---|---|---|
| **Ring 1 — visibility suites** | Semrush (Adobe), Ahrefs, Moz, SE Ranking, Similarweb | Breadth: keywords, backlinks, site audit, rank tracking, traffic intel |
| **Ring 2 — local SEO platforms** | BrightLocal, Whitespark, Moz Local, Yext, Uberall, SOCi, Chatmeter, Birdeye | Listings, reviews, local audits, local rank tracking |
| **Ring 3 — geo-grid specialists** | Local Falcon, Local Viking, GeoRanker, Places Scout, Nightwatch | Map-pack rank tracking on geographic grids |
| **Ring 4 — AI-visibility trackers** | Profound, Peec AI, Otterly.ai, Semrush One AIV, Ahrefs Brand Radar | Brand presence/citations/sentiment inside AI answers |

The parity bar below is the **union of capabilities that recur across these
rings**. Presence of a feature wins no deals; absence disqualifies. The goal
of milestones M3–M6 is that no evaluation of Yanki dies on a missing
table-stakes row.

**Legend — "Yanki today":** ✅ has it (live or merged) · ◐ partial / seed
exists · ✖ missing. **Verdict:** `REQUIRED` = parity gap to close (mapped to a
milestone) · `DIFF` = beyond parity, see
[differentiators.md](differentiators.md) · `DEFER` = deliberately not built
until the stated gate.

---

## 2. Category-by-category analysis

### 2.1 GEO monitoring (generative engine optimization)

Measuring whether and how a brand appears in AI-generated answers. This is
Yanki's founding surface — the strongest area of the product today.

| Feature | What it does | Why users need it | Yanki today | Verdict |
|---|---|---|---|---|
| Brand mention detection in AI answers | Detects whether the brand appears in an engine's answer to buyer-intent questions | The core "am I visible?" question | ✅ footprint step: deterministic matching (diacritic/hyphen/İ-fold tolerant), matched snippet stored | Has — keep |
| GEO score | A single number for AI-answer visibility | Executives and clients need one trendable KPI | ✅ primitive score (mentions ÷ responses); measured/simulated audit adds richer signals (PR #11) | ◐ → weighted 0–100 score (position × sentiment) is **REQUIRED** (M4) |
| Grounded measurement (search-backed) | Answer generation grounded in real web search, with the evidence retained | Ungrounded scores are dismissed as "probabilistic guesswork" | ✅ measured mode: Tavily search → grounded answer via OpenRouter, evidence persisted in `geo_records` | Has — document + productize (M4) |
| Visibility drivers & gaps | Explains *why* visibility is high/low per category (product, trust, content, distribution…) | Users buy "what do I do", not raw data | ◐ `geo_records` stores drivers/gaps; `reliability.py` audits claims against evidence; **no UI beyond results page, no docs** | **REQUIRED** to surface properly (M4) |
| Recommendations / interventions | Prescriptive actions from detected gaps | Closes the insight → action loop | ◐ `interventions.py` + `intervention_library.json` exist (341-line library), unwired to UI/API | **REQUIRED** (M4); expands into differentiator D2 |
| Multi-engine panel | Same prompts across ChatGPT, Perplexity, Gemini, Claude, Copilot | Engines disagree; users need per-engine truth | ◐ adapters exist (Anthropic, OpenAI, Gemini, Perplexity + OpenRouter); **runner currently wired to measured/simulated single-path** (PR #11) | **REQUIRED**: restore explicit multi-engine tracking as a product surface (M4) |
| Local/geo-conditioned GEO | "best dentist **near Kadıköy**" — AI answers conditioned on location | The baseline report's core thesis: nobody fuses local + AI visibility | ✖ | **REQUIRED** (M4, workstream 2 — the report's hero bet) |

### 2.2 AI visibility (AIV)

| Feature | What it does | Why users need it | Yanki today | Verdict |
|---|---|---|---|---|
| Prompt-panel sampling on a schedule | Recurring runs of a tracked prompt set per brand | Visibility is a trend, not a snapshot | ✖ one-shot analyses only; no scheduling of any kind | **REQUIRED** (M4) |
| AI-SoV / share of voice | Brand's share of AI recommendations vs competitors | The agency-facing story; turns rankings into market share | ◐ checker computes competitors-that-appeared (read-time); no SoV metric | **REQUIRED** (M4) |
| Sentiment & position in answers | How the brand is described and where it sits in shortlists | Mention ≠ endorsement; position drives clicks | ◐ audit records carry signal extraction; not scored/surfaced | **REQUIRED** (M4) |
| Citation tracking (AI sources) | Which pages/domains engines cite when answering | "Get cited" is the new "get ranked"; identifies the pages to optimize | ✅ `geo_records` citation metrics + per-analysis `citation_summary` (PR #11); UI shows citations table | ◐ Has core; needs trend + drill-down (M4) |
| AI Overviews / AI Mode tracking | Presence in Google's AI answer box specifically | The largest AI answer surface by traffic | ✖ (admitted gap; SearXNG covers organic results, not the AI box) | **REQUIRED** (M4; needs a data-vendor decision) |
| Model/version provenance | Record engine + model + date per sample | Answers drift across model versions; trust demands provenance | ✅ engine/model recorded per response; "as-of" shown | Has |
| Confidence / sampling honesty | Repeated samples, variance disclosure | Single-sample claims are the category's credibility wound | ◐ 2-samples-per-prompt planned, not built; reliability auditor exists | **REQUIRED** (M4) |

### 2.3 Brand monitoring

| Feature | What it does | Why users need it | Yanki today | Verdict |
|---|---|---|---|---|
| Brand mention alerts (web/AI) | Notify when the brand appears/disappears in tracked surfaces | React in hours, not at month-end | ✖ (operator email on new analyses only) | **REQUIRED** (M4 alerts engine) |
| Competitor brand tracking | Same monitoring for named competitors | Benchmarks make numbers meaningful | ◐ competitors extracted per analysis; not tracked over time | **REQUIRED** (M6) |
| Reputation/review monitoring | Reviews across Google/Facebook/Yelp with sentiment | Local conversion + ranking signal; highest willingness-to-pay in local | ✖ | **REQUIRED** for local ICP (M5; V1-critical in baseline report) |
| Brand-voice AI reply drafts | Draft review responses in brand voice, approval-gated | Saves hours; consistent tone | ✖ | Parity for local suites — (M5, after review ingestion) |

### 2.4 Citation tracking (local citations / NAP)

*"Citation" in the local-SEO sense: structured business listings.*

| Feature | What it does | Why users need it | Yanki today | Verdict |
|---|---|---|---|---|
| Citation monitoring (~top 40 directories) | Find existing listings, diff Name/Address/Phone accuracy | NAP consistency is a ranking + trust factor | ✖ | **REQUIRED** (M5) |
| Citation building | Create/fix listings (service or aggregator) | Agencies bill for this monthly | ✖ | DEFER to M5+ (monitor-first: 60% of value at 10% of complexity — baseline §6.3) |
| Listings sync (aggregator) | Push canonical data to directories, suppress rogue edits | Enterprise/multi-location compliance | ✖ | DEFER (M8; needs aggregator contract + per-loc COGS) |

### 2.5 SERP analysis

| Feature | What it does | Why users need it | Yanki today | Verdict |
|---|---|---|---|---|
| Organic presence check | Does the brand appear in ordinary results for buyer queries | The classic half of visibility | ✅ SERP visibility via self-hosted SearXNG (ADR-28/29), live in prod | Has (binary, one-shot) |
| SERP feature detection | Packs, PAA, AI Overviews, images per query | Knowing *what occupies the page* changes strategy | ✖ | **REQUIRED** (M6) |
| Localized SERP retrieval (gl/hl, coordinates) | Results as seen from a city/point | Local truth requires local SERPs | ✖ (SearXNG language pinned `en`, no geo conditioning) | **REQUIRED** (M4-local / M6) |
| SERP history | Stored snapshots over time | Diagnose when/why a change happened | ✖ one-shot, never re-measured (tech-debt #35) | **REQUIRED** (M6) |

### 2.6 AI answer monitoring

Covered by 2.1/2.2 — the recurring, scheduled, per-engine tracking of AI
answers with raw-answer retention. Yanki's "every raw answer one click away"
wedge already exists on the results pages (✅) ; the **recurring** part does
not (✖ → M4).

### 2.7 Search engine tracking (rank tracking)

| Feature | What it does | Why users need it | Yanki today | Verdict |
|---|---|---|---|---|
| Keyword rank tracking (organic) | Track positions per keyword × location × device over time | The retention engine of every suite; daily-return habit | ✖ | **REQUIRED** (M6) |
| Map-pack / geo-grid tracking | Rank at every pin of a lattice around a location | The baseline report's hero feature; street-level proof | ✖ | **REQUIRED** for the Geo thesis (M4 workstream 2 / M6) |
| Multi-engine coverage (Google/Bing/Apple) | Beyond-Google surfaces | Diversification; Apple Maps rising | ✖ | DEFER (M6+, fast-follow) |
| Ranking history & trends | Time-series storage + trend UI | Proof of progress; renewal conversations | ✖ (no time-series model at all) | **REQUIRED** (M4 foundation, used by M6) |

### 2.8 Competitor monitoring

| Feature | What it does | Why users need it | Yanki today | Verdict |
|---|---|---|---|---|
| Named competitor sets per project | User-pinned benchmark list | Honest benchmarks need stable sets | ◐ KYC extracts competitors; no persistent project/competitor model | **REQUIRED** (M1 gives projects; M6 gives tracking) |
| Auto-discovery of competitors | Surface who actually appears for your queries | Users don't know their AI-era competitors | ✅ competitors-that-appeared (checker + KYC grounding) | Has — extend to trends (M6) |
| Side-by-side visibility / gap views | Your score vs theirs, where they win | Expands seats to strategy roles; upsell | ✖ | **REQUIRED** (M6) |
| Competitor backlink/keyword gap | What links/keywords they have that you don't | Actionable acquisition lists | ✖ | **REQUIRED** (M2 backlinks / M6 keywords) |

### 2.9 Prompt tracking

| Feature | What it does | Why users need it | Yanki today | Verdict |
|---|---|---|---|---|
| Prompt panels per brand/project | A versioned, editable set of tracked questions | "Keyword research for GEO"; the unit of recurring measurement | ◐ deterministic generation from KYC + fixed checker set (versioned `checker-en-v1`); no user editing, no persistence as a panel | **REQUIRED** (M4) |
| Prompt suggestions from site/category | Generate candidate prompts from the customer's own site | Small brands get real signal, not junk from a global DB | ✅ category-topic prompt generation, brand-leak invariant (ADR-27) | Has — expose for editing (M4) |
| Prompt performance history | Score per prompt over time | Shows which questions move the business | ✖ | **REQUIRED** (M4) |

### 2.10 Keyword intelligence

| Feature | What it does | Why users need it | Yanki today | Verdict |
|---|---|---|---|---|
| Keyword research (volume/difficulty/intent) | Discover queries worth targeting | The daily-engagement feature of Ring-1 suites | ✖ | **REQUIRED** (M6, **licensed data** — baseline: no owned index before $3M ARR) |
| Local keyword suggestions (category × city) | Pre-fill tracking sets for local businesses | Local sets are small and service-driven | ◐ category-topic pools exist for prompts | **REQUIRED** (M6, reuse prompt topic engine) |
| Keyword tagging/groups | Organize by service line | Reporting by what the client sells | ✖ | **REQUIRED** (M6) |

### 2.11 Entity monitoring

| Feature | What it does | Why users need it | Yanki today | Verdict |
|---|---|---|---|---|
| Entity extraction & resolution | Recognize the brand as an entity across surfaces (aliases, domains) | Everything downstream keys on "is this us?" | ✅ KYC profile: company, aliases, products, grounded against the crawl (ADR-26/27); `entities_associated_with_brand` audit | Has — strong foundation |
| Knowledge-panel / entity-home monitoring | Track the brand's Google knowledge panel, Wikipedia/Wikidata presence | AI engines lean on entity homes; errors propagate into answers | ✖ | **REQUIRED** (M5) |
| Entity consistency (site ↔ listings ↔ answers) | Diff the canonical profile against what surfaces say | The local-era NAP check, generalized to AI | ✖ (KYC is per-analysis, no canonical record) | **REQUIRED** (M5) |
| Schema/structured-data validation | Validate Organization/LocalBusiness markup | The machine-readable entity feed | ✅ Site Audit validates Schema.org types/properties (PR #23; ontology-bounded) | ◐ Has checks; entity-centric view is M5 |

### 2.12 Content intelligence

| Feature | What it does | Why users need it | Yanki today | Verdict |
|---|---|---|---|---|
| Content gap vs answers | Which questions you're absent from and what cited pages have | Feeds the content roadmap | ◐ raw ingredients exist (citations + gaps) | **REQUIRED** (M6) |
| AI-readability of content | Is the content legible to answer engines (JS-dependence, robots) | Content that can't be read can't be cited | ✅ SEO/AI-readiness audit A–F (ADR-31) | Has — category-leading honesty |
| Content generation (briefs, local pages, GBP posts, replies) | Draft content at scale | Ring-1/2 parity; agencies expect it | ✖ | DEFER to M7 (with EU AI Act Art. 50 labeling — differentiator framing) |

### 2.13 Backlink analysis

| Feature | What it does | Why users need it | Yanki today | Verdict |
|---|---|---|---|---|
| Backlink index/discovery, monitoring, new/lost, toxic, referring domains, anchors, authority metrics, velocity, competitor gap, outreach, alerts, history, exports | See [backlink-intelligence-plan.md](backlink-intelligence-plan.md) — the full module plan | Backlinks remain the #2 evaluated capability in every suite comparison; agencies expect it on one bill | ✖ nothing exists | **REQUIRED — Milestone M2, second-highest priority (operator directive 2026-08-05).** Licensed index first (Ahrefs-class crawler explicitly out of scope pre-$3M ARR) |

### 2.14 Technical SEO

| Feature | What it does | Why users need it | Yanki today | Verdict |
|---|---|---|---|---|
| Site crawler | Fetch site pages respecting robots, budgets | Foundation of every audit | ✅ two: pipeline discovery crawl + Site Audit crawler (Chromium-rendered, PR #23) | Has — **hardening unresolved** (site-audit-integration.md; #55) |
| Technical audit checks | Status codes, redirects, canonicals, meta, OG, hreflang, speed | The consultant-grade fix list | ◐ Site Audit rules + SEO/AI-readiness checks; breadth below Ring-1 auditors | **REQUIRED** to broaden (M3) |
| JS-rendering comparison | Raw vs rendered HTML diff | SPA sites fail AI crawlers silently | ✅ raw + rendered captured (Site Audit); JS-dependence check (ADR-31) | Has |
| Core Web Vitals / performance | Lab/field speed metrics | Standard in every audit | ✖ | **REQUIRED** (M3) |
| Log-file / crawl-budget analysis | How bots actually crawl you | Enterprise SEO staple | ✖ | DEFER (M8) |

### 2.15 Site audits

| Feature | What it does | Why users need it | Yanki today | Verdict |
|---|---|---|---|---|
| Project-based recurring audits | Authenticated projects, repeated runs, one queued/running at a time | Audits are a cadence, not an event | ✅ `seo_projects` / `site_audits` / `site_audit_pages` + APIs (PR #23) | Has (backend); **no UI** → M3 |
| Health score + issue severity | Stable codes, severities, per-page details | Prioritization; trend of debt | ✅ health score capped by critical failures; stable finding codes | Has |
| AI-readiness audit | Can answer engines read the site at all (robots on AI crawlers, JS-only content) | The "why" behind a zero GEO score; no classic tool leads with this | ✅ A–F grade, critical-cap, honest minor-weighting (ADR-31) | Has — **differentiating honesty; keep** |
| Local audit (GBP completeness, NAP, local schema) | Local-specific audit flavor | Local ICP staple (BrightLocal) | ✖ | **REQUIRED** (M5) |
| llms.txt / AI-policy checks | Check emerging AI-crawler policy files | Agent-era table stakes forming now | ✖ (tech-debt #48) | **REQUIRED**, cheap (M3) |

### 2.16 Crawling

Covered by 2.14/2.15. Parity notes: bounded budgets ✅, robots respect ✅
(incl. redirected-origin policies), SSRF/public-host guard ✅ shared, but the
**production egress/isolation design for the Chromium crawler is explicitly
unresolved** (site-audit-integration.md) — a **REQUIRED** M3 hardening item
before audits run against untrusted targets at scale.

### 2.17 Indexing

| Feature | What it does | Why users need it | Yanki today | Verdict |
|---|---|---|---|---|
| Index-status checks (site:, GSC coverage) | Is the page in Google's index | "Not indexed" explains "not ranking" | ✖ | **REQUIRED** (M3, via GSC OAuth read) |
| Sitemap validation | Sitemaps parse, URLs respond | Hygiene every auditor reports | ✅ sitemap read/bounded in Site Audit crawl | ◐ validation reporting → M3 |
| GSC/GA4 integration (read) | Impressions/clicks/coverage in-product | Data where users already live; unlocks "indexed but invisible" | ✖ | **REQUIRED** (M3/M6 integrations) |

### 2.18 Reporting

| Feature | What it does | Why users need it | Yanki today | Verdict |
|---|---|---|---|---|
| Dashboards (per project/workspace) | KPI tiles, trends, latest results | The Monday-morning screen | ✖ (results pages per analysis only) | **REQUIRED** (M4) |
| Report builder (PDF + live link) | Modular, scheduled, brandable reports | Agencies literally resell these; the #1 retention artifact | ✖ | **REQUIRED** (M6; white-label at 2.25 below) |
| Scheduled email digests | Weekly summary to stakeholders | Re-engagement channel | ✖ (waitlist/ops mails only) | **REQUIRED** (M4) |
| Export (CSV/XLSX) everywhere | No lock-in fear; analyst workflows | Table stakes for pro buyers | ✖ | **REQUIRED** (M3+, trivial per-surface) |
| Looker Studio connector | BI-native reporting | Agency stack staple | ✖ | DEFER (M7, needs API v1) |

### 2.19 Alerts

| Feature | What it does | Why users need it | Yanki today | Verdict |
|---|---|---|---|---|
| Threshold/event alert rules | Score drop >X, new competitor in answers, audit regression | React same-day; the re-engagement loop | ✖ | **REQUIRED** (M4) |
| Channels: email, Slack, webhook, in-app | Meet users where they work | Slack is the agency inbox | ◐ email infra exists (Resend); no rules, no Slack, no webhooks | **REQUIRED** (M4; webhooks M7) |
| Digest bundling / dedup / quiet hours | Prevent alert fatigue | Fatigue kills the channel | ✖ | **REQUIRED** with the engine (M4) |

### 2.20 Team collaboration

| Feature | What it does | Why users need it | Yanki today | Verdict |
|---|---|---|---|---|
| Organizations / workspaces / projects | Access mirrors the agency's client book | The B2B spine; per-client isolation | ✖ (User + AuthSession only; accounts grant nothing — #52) | **REQUIRED — Milestone M1 (Admin Platform)** |
| Seats, invitations, roles | Team access with capability ceilings | NRR engine; junior leverage | ✖ | **REQUIRED** (M1) |
| Client viewer seats (free) | Read-only client access, isolated lanes | The wedge vs per-seat incumbents | ✖ | **REQUIRED** (M1 model; M6 client portal) |
| Comments / tasks on evidence | Work where the data lives | Lightweight, not a PM tool | ✖ | DEFER (M7) |

### 2.21 API

| Feature | What it does | Why users need it | Yanki today | Verdict |
|---|---|---|---|---|
| Public read API + keys + docs | Programmatic access to results | Custom dashboards; enterprise requirement | ✖ (internal API only; no keys) | **REQUIRED** (M7; key management ships with M1 admin) |
| Write API (trigger scans) + webhooks | Automation in/out | The integration economy | ✖ | **REQUIRED** (M7) |
| MCP server / agent-readiness | AI agents operate the platform | 2026 buyers wire agents into their stack; Local Falcon already ships MCP | ✖ | DIFF (M7/M9 — differentiator D5) |
| OpenAPI spec published | Machine-readable contract | Baseline dev-ex | ✅ generated `openapi.json` is already the FE contract | Has (internal) — publish at M7 |

### 2.22 Integrations

| Feature | What it does | Why users need it | Yanki today | Verdict |
|---|---|---|---|---|
| Google Business Profile (OAuth) | Locations, reviews, posts, insights | The core local data source | ✖ | **REQUIRED** (M5) |
| GSC / GA4 (read) | Search + analytics context | "Indexed? Clicked?" | ✖ | **REQUIRED** (M3/M6) |
| Slack | Alerts where agencies live | Cheap, high-retention | ✖ | **REQUIRED** (M4) |
| Zapier / Make | Long-tail automation | Buyers check the logo wall | ✖ | DEFER (M7) |
| Stripe (billing) | Subscriptions, metering | Monetization plumbing | ✖ | **REQUIRED** (M1 — admin plan/quota management is built against it) |

### 2.23 Automation

| Feature | What it does | Why users need it | Yanki today | Verdict |
|---|---|---|---|---|
| Scheduled recurring runs | Weekly/monthly tracking cadence | The product's heartbeat | ✖ (queue exists — Postgres `SKIP LOCKED` — but nothing schedules) | **REQUIRED** (M4) |
| Playbooks (trigger → action) | Rank drop → task + rescan + notify | Agencies run identical monthly motions; nobody serves this natively | ✖ | DIFF (M7 — differentiator D1) |
| Auto-verification scans | Action taken → verification scheduled | Closes the loop; builds the prediction dataset | ✖ | DIFF (M7) |

### 2.24 White-label

| Feature | What it does | Why users need it | Yanki today | Verdict |
|---|---|---|---|---|
| White-label reports (logo → full theme) | Agency-branded deliverables | Agencies resell these; decision criterion #1 for the ICP | ✖ | **REQUIRED** (M6) |
| Client portals / custom domains | Branded live dashboards | "Their own platform" feel at mid-tier price | ✖ | **REQUIRED** (M6; domain/email infra) |
| Lead-gen widgets | Embeddable checkers for agency sites | SE Ranking/BrightLocal parity; growth loop | ◐ the public checker exists (dark) and is embeddable-adjacent | DEFER (M7) |

### 2.25 Enterprise capabilities

| Feature | What it does | Why users need it | Yanki today | Verdict |
|---|---|---|---|---|
| SSO (SAML/OIDC) + SCIM | IdP-managed access | Procurement gate | ✖ | DEFER (M8 — deliberately sequenced late; baseline §6.3) |
| Audit logs (visible) | Who did what, when, from where | Security review staple | ✖ (events not even emitted yet) | **REQUIRED** — **emit from M1**, viewer UI in M1 admin; org-visible log M8 |
| MFA (TOTP/WebAuthn) | Account security | Table stakes for B2B auth | ✖ | **REQUIRED** (M1) |
| Data residency / DPA / SOC 2 path | Compliance posture | Enterprise + EU/TR buyers | ✖ | DEFER (M8; keep `region` on org from M1 schema) |
| Quotas, rate limits, spend caps per org | Governance of consumption | Cost control at scale | ◐ global/IP caps exist (P5.0/P5.6); nothing per-org | **REQUIRED** (M1) |

### 2.26 Billing & plans (cross-cutting parity)

| Feature | What it does | Why users need it | Yanki today | Verdict |
|---|---|---|---|---|
| Stripe subscriptions, tiers, proration, dunning | Self-serve monetization | Nothing sells without it | ✖ | **REQUIRED** (M1 — admin needs plans/quotas as first-class objects) |
| Credit/usage metering + ledger | Scan/AI credits with allowances | COGS pass-through with margin; the baseline's pricing architecture | ✖ (per-response `cost_usd` recorded — the seed) | **REQUIRED** (M1 metering foundation; consumer UX M4+) |
| Contextual upgrade paths | Smallest-unlock offers at limits | Conversion at the moment of need | ✖ | DEFER (M4+, needs limits first) |

---

## 3. Parity scoreboard (summary)

Counting the rows above: **~14 Has/◐-strong**, **~40 REQUIRED**, **~12
DEFER/DIFF**. The Has column clusters exactly where the team has been
building since July: the GEO measurement engine, grounded evidence, SERP
presence, AI-readiness auditing, and the beginnings of Site Audit. The
REQUIRED column clusters in everything **around** the engine: tenancy, RBAC,
billing, scheduling, history, dashboards, reporting, alerts, keywords, rank
tracking, backlinks, integrations. That is precisely why the roadmap starts
with the **Admin Platform (M1)** — every REQUIRED row either depends on
org/project/quota primitives or is worthless without them — and **Backlink
Intelligence (M2)** as the largest single missing suite capability.

## 4. Coverage map — parity category → milestone

| Category (task brief) | Milestone home |
|---|---|
| GEO monitoring, AI visibility, AI answer monitoring, prompt tracking, ranking history (foundation), alerts, brand monitoring (AI), reporting (dashboards/digests) | **M4** |
| Team collaboration (orgs/seats/roles), enterprise quotas, MFA, audit-event emission, billing/plans, API keys (mgmt) | **M1** |
| Backlink analysis (all rows) | **M2** |
| Technical SEO, site audits, crawling, indexing, exports (first pass) | **M3** |
| Citation tracking (local), entity monitoring, GBP integration, review/reputation, local audit | **M5** |
| Keyword intelligence, search engine tracking, SERP analysis (features/history), competitor monitoring, content intelligence, white-label reporting & portals | **M6** |
| Automation (playbooks), API (public/read/write/webhooks/MCP), integrations (Zapier/Looker), content generation, collaboration (comments/tasks) | **M7** |
| Enterprise (SSO/SCIM, residency, SOC 2, listings sync, log-file analysis) | **M8** |
| Prediction, autonomous agents, data network | **M9** |

Every category from the re-planning brief has exactly one home; nothing is
unassigned. The milestone details live in [roadmap.md](roadmap.md).
