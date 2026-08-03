# Yanki — Product Roadmap

*Audience: leadership + engineers. This is the **product** roadmap — the phased
path from the MVP we are building now to the transparent, affordable Semrush
alternative described in [00-first-mvp-draft.md](00-first-mvp-draft.md).*

**Scope authority is [02-mvp.md](02-mvp.md), not this file.** If it isn't in
02-mvp.md, it isn't in the MVP — it's a phase below. **Scope is frozen until day
60.** New ideas go to the backlog, not the sprint.

**This is the *what/why/when*, not the *how*.** The engineering task breakdown —
tickets, sequencing, owners — lives in
[implementation-plan.md](implementation-plan.md). Where a phase item needs build
detail, follow the link; this file does not duplicate it.

The three wedges every phase serves (from the draft): **show our work**
(published methodology, every raw answer one click away), **pricing agencies can
scale on**, and **Turkish as a first-class language** *(⚠ operator decision
2026-07-10: Turkish is **deferred to Later** — the whole product launches
English-only; the wedge stays on the roadmap but is not launch scope. See 2c.)*.

---

## Phase map at a glance

| Phase | Horizon | Theme | Buyer it unlocks |
|---|---|---|---|
| **Now** | This session | Prove the core loop: URL → GEO score, anonymous | Nobody yet — internal proof |
| **Next** | Weeks 2–8 | Public checker + real product: accounts, billing, weekly tracking, Turkish, competitors | Founder → In-house SEO → Agency |
| **Later** | Day 60–90+ | Scale the wedges: agency plan, AI Overviews, Arabic, export/API, compliance | Agency at volume + enterprise inbound |

---

## Now — the MVP (this session)

**Goal:** the entire loop in [02-mvp.md](02-mvp.md) works end-to-end on a live
stack — *URL in → GEO score out in ~10 minutes, with every raw answer behind
it* — and runs at $0 under `DRY_RUN=1`. This is the sole definition of done for
the session; nothing here is negotiable and nothing below it ships first.

| Item | Rationale |
|---|---|
| Anonymous URL submission (no auth) | Lowest-friction proof the loop delivers a defensible number; auth is pure overhead until we have paying users. |
| Discovery → KYC → prompts → execute → footprint → scoring pipeline | The six steps ARE the product; everything later is packaging, cadence, and depth on top of this spine. |
| Claude + OpenAI real; Gemini + Perplexity stubbed | Two real engines prove multi-engine execution and cost; stubs keep the panel shape without paying for four vendors before validation. |
| Binary footprint + primitive score `footprints / total_responses` | Intentionally primitive so it is a pure, unit-tested, *defensible* function — the "show our work" wedge starts here (ADR-11). |
| Deterministic template prompts (no LLM prompt-gen) | Testable and free; LLM/native prompt generation is a Next-phase quality lever, not a loop blocker. |
| `llm_cache` within a single job's runs | Proves the caching mechanism cheaply; the cross-account version (the real cost lever) is Next. |
| `DRY_RUN=1` mock provider + cost caps (`PROMPT_COUNT`, `MAX_RESPONSES_PER_JOB`) | CI and first-run cost $0; makes Week-1 invoice validation possible before anything goes public. |
| **Served at `https://yanki.beyondkaira.com`** from the shared beyondkaira VPS (161.97.172.146; DNS set 2026-07-10), behind host nginx (originally the shared pulse-prod Caddy; migrated per `deploy/MIGRATION.md`) | Zero new infra for the MVP — reuse the box and TLS terminator we already run. **Hard constraint: the VPS's live sites (pulse, Ant Media, brier) must never be disturbed** — deploys are additive (an nginx *reload*, an isolated compose project, no shared ports). Build detail: P4.2 in [implementation-plan.md](implementation-plan.md). |

**Sequencing:** the pipeline is strictly sequential (discovery must precede KYC,
etc.); build and test each step behind `DRY_RUN` before wiring a real key. This
is the whole session — do not start Next-phase work until the happy path renders
a score. Deployment (P4.2) is the last MVP step, after the real-key cost check
(P4.1), and is supervised.

---

## Next — free checker + the real product (roughly weeks 2–8)

The draft's build plan: **checker ships weeks before the app** (it is the demand
test, lead magnet, and launch asset in one), then the full self-serve product.
Ordered by the draft's Launch 1 → Launch 3 sequence.

### 2a. Free public checker — the launch wedge (weeks 3–4, ships first)

*Engineering decomposition done (session 3): **Phase 5, P5.1–P5.11** in
[implementation-plan.md](implementation-plan.md) — build stays frozen behind the
MVP sign-off gate (P4.1 + P4.2 + first green CI).*

| Item | Rationale |
|---|---|
| Public no-signup page: brand + category → 12 fixed prompts × 4 engines, live | Every run is a demand signal and a lead; Semrush has a checker, ours must be more generous and exist in Turkish (theirs doesn't). |
| Score + engine-by-engine presence map + competitors that showed up + ≥1 full raw answer | "Show our work" from the first touch — not a teaser; the full report costs an email address (lead capture). |
| Results cached 24h per brand, rate limited, email-gated | Abuse control: caching, rate limits, email gate, fixed prompt set, daily cost check (the draft's checker-abuse mitigation). |
| ~~**English + Turkish** at checker launch~~ **English-only at launch** (operator decision 2026-07-10) | The draft called Turkish a launch differentiator; the operator chose to ship the whole product EN-only and defer Turkish to Later. The original rationale stands whenever it is revived. |
| **Waitlist + email notifications** (operator addition 2026-07-10, built same day as P5.13): home-page signup → thank-you mail + operator alert; every analysis run alerts the operator | Lead capture starts BEFORE the checker goes loud, and the operator sees demand in their inbox in real time (runs are recorded in the DB regardless). Resend-backed, fail-open, delivery gated on domain verification. |

### 2b. Engine + scoring depth — make the number trustworthy

| Item | Rationale |
|---|---|
| Real Gemini (with search grounding) + Perplexity engines | Four real engines with grounding are the actual panel; Gemini-with-grounding stands in for Google's AI-answer surface until AIO tracking (Later). The *organic* Google surface is now measured separately — SERP visibility from an open-source metasearch instance shipped 2026-08-03, off by default (ADR-28). |
| 2 samples per prompt, frequencies not single observations | LLM answers wobble; sampling + frequencies is how we avoid the "guesswork" reputation the category earned. |
| Weighted AI Visibility Score 0–100: mention × position (1.0 / 0.7 / 0.4) × sentiment (1.0 / 0.9 / 0.5), averaged, ×100 | The defensible, published score the product sells on; the MVP's binary score is the honest placeholder until this lands. |
| Sentiment + position extraction pass (cheap model) | Inputs to the weighted score; a cheap analysis model is one of the three cost protections. |

> **Input side, delivered in two passes.**
> [`docs/discovery-kyc-improvements.md`](discovery-kyc-improvements.md) was the
> first: **steps 1, 2a, 3, 4 and 5 are implemented** — JSON-LD extraction,
> diacritic and hyphen tolerance in footprint matching, a KYC parse repair plus
> one bounded retry, a Content-Type guard on page fetches, and a gate that
> refuses the paid execute fan-out on a profile with no company or no topic.
> **Steps 2b and 6 are not built:** they would revive §2c scope and stay gated on
> an operator decision — see §2c immediately below.
>
> [`docs/pipeline-quality-plan.md`](pipeline-quality-plan.md) is the second
> (2026-08-01), and takes the same three steps from MVP to product grade:
> encoding-correct decoding, binary sniffing, a homepage retry, scored link
> selection and cross-page boilerplate removal (discovery); sanitation of every
> field plus **grounding** — a product, competitor or alias the model returned
> that is nowhere in the crawl is dropped, because a hallucinated alias inflates
> the score and nothing downstream can tell — and two new profile fields
> (`category`, `use_cases`) so the buying category is *asked for* rather than
> inferred (KYC); a category filter that keeps spec attributes out of questions,
> rotation that reaches every topic × shape pair, and a hard invariant that no
> scored question may name the brand it measures (prompts). All of it is
> language-neutral and adds **no** paid call.
>
> **Readiness side, shipped 2026-08-03 (ADR-31), the same push.** The GEO and
> SERP scores say *whether* AI answers and search results name a company; neither
> says *why* when the answer is no, and "why" is the only part a customer can act
> on. The **SEO / AI-readiness audit** is that "why": it re-reads the crawl
> discovery already paid for — plus a single `/robots.txt` fetch, no extra crawl,
> no paid call — and returns an A–F **grade** with the failing checks behind it.
> It leads with the checks that are AI-specific and that no classic SEO tool looks
> at: whether the answer engines' crawlers are allowed in at all (a `robots.txt`
> block means the site *cannot* appear in their answers — separating a retrieval
> block that costs answers today from a training block that only erodes presence
> over time), and whether the page says anything without JavaScript (most AI
> crawlers don't run it). The grade is **capped by critical failures** so a
> weighted average can't average a fatal problem away, and classic hygiene (meta
> description, canonical, Open Graph) is weighted minor and labelled as such —
> honest about which checks are really about AI. What it is **not**: not a rank or
> a rank tracker, not the weighted 0–100 AI Visibility Score above (that scores
> *presence*; this scores *legibility*), and **not** Google AI Overviews tracking
> (Later, below) — it audits *this* site's own files, it does not read Google's
> answer box. It runs on every URL analysis (`result.seo` is null where there was
> no site to read, e.g. a checker submission); it is language-neutral.

### 2c. Turkish as a first-class language — the wedge that can't be a sprint bolt-on

> **⚠ Deferred to Later — operator decision, 2026-07-10.** The whole product
> ships English-only for now; everything in this subsection moves to the
> Later bucket and is revived only on the operator's word. Consequence,
> stated honestly: the "Turkish first-class" wedge is not part of the launch
> story until then, and the Arabic gate below ("Turkey delivers 20%+ of
> signups") cannot trigger while Turkish is off. Engineering decomposition
> (P5.8/P5.9) is preserved in implementation-plan.md as skipped cards.
>
> **Two items below now have a written, ready-to-build spec and are waiting only
> on that word** (2026-07-28): "Turkish suffix-aware brand/footprint matching" is
> step 2b of [`discovery-kyc-improvements.md`](discovery-kyc-improvements.md),
> and step 6 (record `<html lang>` / ccTLD into the KYC profile) is the missing
> *input* that native Turkish prompt generation needs. Neither is implemented.
> The language-neutral half of the matching work (step 2a — diacritic folding and
> hyphen/space equivalence, which helps Nestlé and Coca-Cola as much as anything
> Turkish) **has** shipped and is not part of this deferral; a test asserts the
> suffix behaviour stayed unchanged, so the line between the two is enforced in
> CI rather than by memory.

| Item | Rationale |
|---|---|
| Native Turkish prompt generation (written how Turkish users ask, not translated) | If the Turkish numbers are wrong the whole differentiation story dies on day one — this is explicitly not the corner we cut. |
| Turkish suffix-aware brand/footprint matching | Turkish agglutination breaks naive string matching; footprint accuracy in TR depends on it. |
| Extraction model validated on a labelled Turkish test set before launch | A precision bar before public launch + weekly human spot-checks in beta keeps the numbers honest. |

### 2d. The app: accounts → billing → cadence

| Item | Rationale |
|---|---|
| Auth, accounts, projects + onboarding wizard (brand, site, category, up to 5 competitors, language) | Turns the anonymous loop into a product people return to; first run kicks off immediately with live progress. |
| Prompt engine: 30–60 prompts from the site + category, user edits/approves, versioned panels with annotations | "Keyword research" for GEO; site-derived panels give even small brands real signal (fixes the "small brands get junk" gap). |
| Stripe billing, Free / $49 / $129 from day one of public launch, hard caps + in-context upgrade | Category has a proven price anchor; hard limits + upgrade-at-cap protect margin. Reprice to $59/$149 *before* launch if Week-1 invoices run high — never after. |
| Weekly scheduling (top prompts weekly, full panel monthly) + weekly digest email + alerts | The recurring loop is the retention engine; alerts fire on score move ≥10pts, competitor enters a priority answer, or you disappear from one — max one alert mail/day. |
| **Cross-account `llm_cache`** (identical prompt+engine cached 24h across accounts) | The big cost lever — the MVP's within-job cache generalized; central to hitting "API cost < 35% of plan price". |
| Answers Explorer: every metric links to the raw answers behind it | The trust feature — no dead ends; this is the "show our work" wedge as UI. |
| Competitor share-of-voice, mention rate per engine, average position, citations (own pages vs third-party) | Share-of-voice is the agency-facing story; the third-party citation list is quietly the best screen in the product. |

**Sequencing:** checker (2a) ships first as the demand test and recruits 5 design
partner agencies on free Pro; engine/scoring depth (2b) and Turkish (2c) run in
parallel because the checker needs both to be credible; the app (2d) follows with
partners in beta, billing in test, then public launch. Detailed tickets:
[implementation-plan.md](implementation-plan.md).

---

## Later — scale the wedges (day 60–90 and beyond)

Deliberately deferred until the checker/app data tells us which wedge to double
down on. Each is gated on a day-90 decision below.

| Item | Rationale |
|---|---|
| **Agency plan ~$299/mo** — 10 projects (kept fully separate) + white-label PDF reports | The agency owner is the multiplier and the highest-leverage buyer; the 5 design partners will "pull the agency plan out of us" when it's time. Day 60–90 decision. |
| **Google AI Overviews tracking** | Half-closed as of 2026-08-03. The *organic* half — whether the brand shows up in ordinary search results for brand-free buyer queries, alongside the AI-answer GEO score — now has a $0 answer: SERP visibility read from a self-hostable open-source metasearch instance (SearXNG, AGPL-3.0), off by default (ADR-28). That retires the old "needs SERP scraping or a paid SERP API" line for organic results — neither is needed. Still open, and still our biggest admitted gap vs Semrush: **Google AI Overviews specifically** — the AI answer box on a Google results page, a different artifact from the organic results SearXNG federates, with no $0 source yet. We keep saying the open half out loud on the comparison page and close it around day 60–90 — hiding it would cost us the transparency story. |
| **Turkish** language support (moved from 2c, operator decision 2026-07-10) | Native prompts + suffix-aware matching + TR UI, as specced in 2c and the skipped P5.8/P5.9 cards. Revive on the operator's word; requires a native-speaker sign-off before any public Turkish. |
| **Arabic** language support | Ship only if Turkey delivers 20%+ of signups organically — proof the native-language playbook repeats before we spend on a third language. (Gate suspended while Turkish itself is deferred.) |
| **CSV export + public API** | Export is a Pro-tier ask already; API is "later, when someone asks and pays" — not needed to prove willingness to pay. |
| **Compliance-grade tier $500+/mo** (accuracy guarantees, audit trails) | Only if regulated/enterprise brands come inbound asking; the pipeline already supports the audit trail, so it's packaging, not a rebuild. |

**Explicitly still NOT building** (from the draft, until someone asks and pays):
content generation, an AI recommendation engine (generic advice is the most
mocked feature in the category — we ship specific findings instead), attribution/
analytics integrations, SSO, mobile, more engines.

---

## Day-90 decision gates

Read the numbers at day 90 and let them pick the next investment (from
[00-first-mvp-draft.md](00-first-mvp-draft.md)):

- **Agencies dominate paying accounts:** build the agency plan next (workspaces,
  white-label PDF).
- **Turkey delivers 20%+ of signups organically:** ship Arabic, double the local
  content.
- **Regulated / enterprise brands come inbound asking about accuracy and audit
  trails:** add a compliance-grade tier at $500+/mo — the pipeline already
  supports it.
- **Free-to-paid under 2%:** stop building, fix packaging and pricing first.

---

## First-90-days success metrics

The targets we recalibrate against after two weeks of real data (from
[00-first-mvp-draft.md](00-first-mvp-draft.md); ranges are ranges, not promises):

- **3000 checker runs, 600 signups, 40 paying, $2.5–4k MRR.**
- **Activation:** 60% of signups see their first snapshot, median under 10
  minutes.
- **Month-2 logo churn under 8%** — the number leadership will actually stare at;
  monitoring tools die of curiosity churn.
- **Run reliability 95%+, API cost per paying customer under 35% of plan price.**

---

## How the MVP's out-of-scope list maps to phases

Every item [02-mvp.md §4](02-mvp.md) marks out-of-scope has a home here — this
table is the contract between "not now" and "when":

| 02-mvp.md out-of-scope item | Phase | Where above |
|---|---|---|
| Auth, accounts, projects | **Next** | 2d — app: accounts |
| Billing / Stripe / plan limits | **Next** | 2d — Stripe Free/$49/$129 |
| Scheduling, recurring scans, weekly digests + alerts | **Next** | 2d — weekly scheduling + digest + alerts |
| Sentiment analysis and position weighting (score stays binary) | **Next** | 2b — weighted 0–100 score |
| Turkish language (native prompts + Turkish suffix matching) | **Later** (operator decision 2026-07-10; was Next) | Later — Turkish (moved from 2c) |
| Cross-account cache (MVP caches within a job only) | **Next** | 2d — cross-account `llm_cache` |
| Real Gemini + Perplexity engines (stubbed in MVP) | **Next** | 2b — real Gemini + Perplexity |
| 2-samples-per-prompt sampling | **Next** | 2b — 2 samples per prompt |
| Competitor comparison, share of voice, citations, Answers Explorer UI | **Next** | 2d — SoV, citations, Answers Explorer |
| CSV export, historical trends | **Next / Later** | Trends land with weekly tracking (2d); CSV export is a Pro feature but full export/API is **Later**. |
| Google AI Overviews tracking | **Later** | AI Overviews tracking |
| Arabic | **Later** | Arabic (gated on Turkey traction) |
| White label, API, SSO, mobile, more engines | **Later** | Agency white-label + export/API; SSO/mobile/more engines stay deferred |
| Compliance / audit-trail tier | **Later** | Compliance-grade $500+/mo tier |
