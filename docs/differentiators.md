# Yanki — Differentiation Proposal

*Audience: founders, PM. What makes Yanki **better** than the field once
[feature parity](feature-parity.md) is achieved. Differentiators are
prioritized **after** parity by operator directive (2026-08-05): the
implementation order is Admin Platform → Backlink Intelligence → remaining
parity (M3–M6) → these (mostly M7–M9). Strategy source:
[Yanki_Geo_Intelligence_Report.pdf](Yanki_Geo_Intelligence_Report.pdf) §2.2,
§13; grounded against what the repo already contains as of 2026-08-05.*

**Status: adopted planning baseline — 2026-08-05 (session 20, ADR-33).**

---

## Ranking criteria

Each differentiator is scored on **impact × feasibility × durability** (the
baseline report's frame). Small UI polish is explicitly excluded — everything
here changes what a buyer can do, not how a screen looks. A differentiator
earns its rank partly by **seeds already in the repo**: Yanki has three
unusual assets no session has productized —

1. **`pipeline/reliability.py`** — an auditor that checks every LLM-extracted
   claim against measured evidence and emits a reliability score. This is
   explainable AI as code, in a category users call "probabilistic guesswork".
2. **`pipeline/interventions.py` + `data/intervention_library.json`** — a
   trigger-matched, deduped, ranked recommendation engine over audit records.
   This is the insight→action loop as code.
3. **The measured path** (Tavily search → grounded answer → citation metrics
   in `geo_records`) — visibility claims with retained evidence.

These make several "hard" differentiators cheap for Yanki specifically.

---

## The differentiators, ranked

### D1 — Prescriptive playbooks: detect → diagnose → recommend → verify (M7)

Every insight ships with an action checklist, an owner, and — the part nobody
does — an **automatically scheduled verification scan** that closes the loop
and records whether the action worked. Incumbents ship dashboards; agencies
buy outcomes-per-hour. The intervention library is the seed; playbooks wrap
it in triggers (score drop, new competitor in answers, audit regression) →
actions (create task, draft content brief, rescan, notify).
**Impact ★★★★★ · Feasibility ★★★★ (seed exists) · Durability ★★★★ (compounds
with every template; the outcome dataset is proprietary).**

### D2 — Explainable, evidence-audited scores ("show our work" weaponized) (M4→M7)

Publish the methodology (already live at `/methodology`), keep every raw
answer one click away (already live), and go one step further than anyone:
attach the **reliability audit** to every AI-derived claim — "this gap claim
is supported by 3 pieces of measured evidence; this one is the model's
opinion, demoted." No competitor exposes a per-claim evidence trail. This
converts the category's biggest grievance (black-box numbers) into Yanki's
brand.
**Impact ★★★★☆ · Feasibility ★★★★★ (reliability.py exists) · Durability
★★★★☆ (trust compounds; hard to retrofit onto a black box).**

### D3 — The Unified Visibility Index: map + organic + AI answers, one number (M4→M6)

The baseline report's core bet: no platform fuses geo-grid map rankings,
organic local rankings, and AI-answer share of voice into one
executive-legible score. Yanki already measures two of the three surfaces
(organic via SearXNG, AI via the GEO engine); the grid completes it. Local-
first AIV — "is my dentist recommended by ChatGPT **in this neighborhood**" —
is unclaimed territory with an estimated 12–18-month copy-lag for an
Adobe-integrating incumbent.
**Impact ★★★★★ · Feasibility ★★★ (grid infra + prompt-sampling COGS) ·
Durability ★★★★★ (category-defining; data moat accrues).**

### D4 — Agency-native economics & tenancy (M1→M6)

Free unlimited client-viewer seats, workspaces that mirror the client book,
white-label at mid-tier (not enterprise-gated), and per-location/per-project
pricing that collapses with volume. This is a *pricing-architecture*
differentiator, which is why the Admin Platform (M1) must model orgs, seats,
plans, quotas, and metering correctly from day one — the wedge is structural,
and post-Adobe Semrush cannot follow it downmarket.
**Impact ★★★★★ · Feasibility ★★★★ (it's schema + billing discipline) ·
Durability ★★★★ (incumbent economics are contractually stuck).**

### D5 — Agent-native platform: full MCP + write API + webhooks + llms.txt (M7)

2026 buyers wire AI agents into their stacks; Local Falcon proved demand by
shipping an MCP server for a single-purpose tool. Yanki does it
platform-wide: every capability (run analysis, read results, draft a reply,
build a report) exposed as scoped, capability-checked, human-approval-gated
agent tools. The audit log (M1) is the prerequisite that makes agent write
access governable.
**Impact ★★★★☆ · Feasibility ★★★★ (API v1 + capability model) · Durability
★★★ (copyable, but early ecosystem lock-in is real).**

### D6 — Autonomous monitoring agents with approval gates (M9)

The playbook engine (D1) graduated: agents that watch every tracked surface,
triage anomalies, draft the response (reply, fix, brief, rescan), and queue
it for one-click human approval. "A two-person team manages a national
footprint" is the JTBD. Guardrails come free from M1 (RBAC, per-key caps,
audit trail).
**Impact ★★★★★ · Feasibility ★★ (needs D1 + volume) · Durability ★★★★.**

### D7 — Predictive visibility modeling (M9)

"If review velocity +20% → expected SoLV lift +x" — forecast the impact of
actions, with backtests and ranges, never point promises. Nobody credible
does this in local/GEO. Requires 12+ months of cross-org outcome data —
which D1's verification scans generate as a by-product. Sequenced last for
honesty: shipping it early on thin data would burn the trust brand (D2).
**Impact ★★★★★ · Feasibility ★ today, ★★★ at month 12 · Durability ★★★★★
(the data is the moat).**

### D8 — The local AIV data network & benchmark reports (M9)

Aggregated, anonymized neighborhood-level AI-answer visibility benchmarks —
"AI recommendation share for dentists, by city" — published as research. A
PR engine, a sales tool, and a dataset competitors cannot buy. Depends on
AIV at scale (M4) + anonymization review (M8 governance).
**Impact ★★★★ · Feasibility ★★ · Durability ★★★★★.**

### D9 — Compliance-as-feature: EU AI Act labeling, KVKK/GDPR toolkit (M7–M8)

Every AI-generated artifact (review replies, report commentary, content)
carries Art. 50-aligned disclosure metadata automatically; per-org AI
kill-switch; no cross-tenant training; data-residency options later. Turns a
regulatory burden into a selling point in exactly the underserved markets
(EU/DACH, TR, Gulf) the GTM targets.
**Impact ★★★ · Feasibility ★★★★ · Durability ★★★ (regulation-driven timing
advantage).**

### D10 — Transparent backlink intelligence (M2, differentiating flavor)

M2 is parity work, but Yanki's version carries the house style: every
authority metric decomposes into its inputs ("show our work" applied to link
scoring), toxicity flags come with the *why*, and the licensed-index
provenance is disclosed rather than laundered as "our index". Cheap to do,
on-brand, and a wedge against the black-box authority scores users already
distrust.
**Impact ★★★ · Feasibility ★★★★★ (policy, not infra) · Durability ★★★.**

---

## What Yanki deliberately does NOT do (anti-strategy)

Unchanged from the baseline report §13, restated so parity work doesn't
creep into it: no PPC/social/PR toolkits, no owned crawler/backlink index
before ~$3M ARR (license instead — see
[backlink-intelligence-plan.md](backlink-intelligence-plan.md)), no consumer
SMB app, no services arm competing with agency customers, no
unlimited-everything pricing that breaks the credit/COGS model, and no
generic AI-advice engine — recommendations must trace to measured evidence
(D2) or they don't ship.

## Sequencing note

D4 starts at M1 by construction (the admin platform *is* its foundation).
D2 and D10 are style-level and ride inside M2/M4 at near-zero cost. D1/D5
anchor M7. D6/D7/D8 are M9 and gated on data volume. This ordering satisfies
the operator's constraint that differentiators follow parity — while the
parity milestones quietly lay every differentiator's foundation.
