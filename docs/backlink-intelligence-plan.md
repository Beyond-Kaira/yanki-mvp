# Yanki — Backlink Intelligence Plan (Milestone M2 — second priority)

*Audience: founder-orchestrator + implementing agents. The complete plan for
Yanki's backlink platform — the second implementation milestone after the
[Admin Platform](admin-panel-plan.md) (operator directive 2026-08-05;
ADR-33). Engineering decomposition lives as **Phase 8** in
[implementation-plan.md](implementation-plan.md). The competitive bar is the
Ring-1 suites' link tooling (Ahrefs — the industry-reference index — Semrush,
Moz, SE Ranking); the strategy constraint comes from the planning baseline:
**license the index, own the layer** — no owned crawler before ~$3M ARR
([Yanki_Geo_Intelligence_Report.pdf](Yanki_Geo_Intelligence_Report.pdf) §6.1,
§13).*

**Status (2026-08-05, session 23): the ENGINE shipped, and is now REACHABLE.**
Built and merged behind `BACKLINKS_ENABLED=0` — B1 (schema + `BacklinkSource`
seam + deterministic mock, five tables, migration 0013), B4's delta engine,
B5 (Yanki Authority), B6 (toxicity + disavow) and B7 (gap + unlinked mentions),
all metered through M1's quota gate and credit ledger. See
`backend/app/backlink/` and implementation-plan P8.1/P8.4/P8.5/P8.6/P8.7.

B3's **API half landed in session 23**: `app/services/backlinks.py` plus
eleven routes under `/api/v1/seo-projects/{id}/backlinks`, registered in
`app/api/main.py`, permission-split (`backlink:view` to read,
`backlink:refresh` to spend, `export:data` to take a copy away) and dark as a
404 — not a 403 — while the flag is off. A refresh runs synchronously against
the mock at $0, records its cost in the credit ledger, and is audited.

**B3 is now complete** (session 23): `/backlinks` and `/backlinks/[projectId]`
ship the inventory, referring domains with their toxicity reasons, anchors,
new/lost events and outreach opportunities, and the nav entry is `live`. The
UI carries the module's honesty rules up to the surface — a null score renders
as `—` and never `0`, an unmeasurable pull is labelled wherever its numbers
appear, and the switched-off state is a first-class screen rather than an
error, because off is what production serves.

**Still open:** B2, the first licensed vendor adapter — blocked on operator
decision **A4** (vendor + budget), so **every number a customer would see today
is fixture data, which is the reason the module stays dark in production**;
XLSX alongside the shipped CSV, and a screen for competitor management (the
API has it); B4's residual — the liveness verifier and scheduled refresh, both
needing worker wiring; and B8.

Anything below that reads as unbuilt should be checked against those cards
before it is built. The `$0` DRY_RUN end-to-end framing still holds: the mock
is a pure function of `(domain, cycle)`, so multi-refresh behaviour is testable
without a clock or a vendor.

---

## 1. Why backlinks, and why second

Backlink analysis is in the "absence disqualifies" tier of every suite
evaluation ([feature-parity.md](feature-parity.md) §2.13): agencies
consolidating tools expect keywords, audits, rank tracking **and links** on
one bill. Yanki has nothing today — the largest single missing suite
capability. It is also newly strategic for the GEO era: AI answers *cite*
sources, and authority/link signals correlate with who gets cited — Yanki
can connect "who links to you" with "who gets cited about you" in a way
link-only tools cannot (differentiator D10 + the citation data already in
`geo_records`).

It comes **after** the Admin Platform because a licensed index bills per
row/request: without per-org quotas, credit metering, and plan gates (M1),
every backlink screen is an uncapped COGS leak.

## 2. Data strategy

- **Primary: licensed index** behind a provider seam — a `BacklinkSource`
  protocol with adapters, exactly the pattern the codebase already uses
  three times (`Provider` for LLMs, `SerpSource` for search, the site-audit
  engine registry). Candidate vendors: DataForSEO-class wholesale APIs
  (first target), Majestic, Moz Links API. **Vendor choice is an operator
  decision (cost + ToS) — operator-expected A4.** Multi-vendor failover and
  per-request cost tagging from day one (the architecture the baseline
  mandates for SERP data applies verbatim here).
- **Mock adapter** with deterministic fixtures so the whole module builds,
  tests, and demos under `DRY_RUN=1` at $0 — the house pattern.
- **Own verification crawler (thin, later stage):** not an index — a
  liveness checker that re-fetches a *sampled subset* of licensed rows to
  verify link presence/anchor/nofollow, feeding freshness confidence and
  the transparency story ("last verified by us: date"). Bounded by the same
  robots/SSRF/net-guard discipline as existing crawlers.
- **Provenance disclosed** (D10): the UI says which index a number comes
  from and when it was fetched. No "our index of 40 trillion links" theater.

## 3. Capabilities (the module, feature by feature)

| # | Capability | What ships |
|---|---|---|
| 1 | **Backlink discovery** | Full backlink inventory per project domain from the licensed index: source URL/domain, target URL, anchor, first/last seen, link attributes (follow/nofollow/UGC/sponsored, redirect, canonical, img/text), page + domain metrics |
| 2 | **Backlink monitoring** | Scheduled refresh per project (plan-gated cadence: weekly Pro / daily Business-class), delta computation into link events |
| 3 | **New backlinks** | Event stream + view of first-seen links per window; feeds alerts and reports |
| 4 | **Lost backlinks** | Links gone since last snapshot, with reason where the source distinguishes (page gone, link removed, nofollow'd, blocked); re-verified by the liveness checker before "lost" is claimed (accuracy = brand) |
| 5 | **Toxic backlinks** | Risk scoring per link/domain: spam signals from the vendor + local heuristics (anchor money-term density, link-farm patterns, TLD/IP clustering). Every flag decomposes into its reasons (D10). Disavow-file export (Google format). Toxicity labels are *advisory* and worded honestly — the category's over-confident "toxic" scores are a known credibility trap |
| 6 | **Referring domains** | Domain-level rollup: count, authority distribution, follow ratio, first/last seen, per-domain link list |
| 7 | **Anchor text analysis** | Anchor distribution (exact/partial/brand/naked/generic classification), money-anchor concentration warnings, competitor anchor comparison |
| 8 | **Authority metrics** | Vendor rank surfaced as-is + **Yanki Authority (transparent)**: a documented, decomposable 0–100 from referring-domain count/quality/relevance — formula published on the methodology page like the GEO score. Never presented as PageRank |
| 9 | **Link velocity** | New-vs-lost trend per week/month; velocity vs named competitors; anomaly detection feeding alerts |
| 10 | **Competitor backlinks** | Track competitor domains' profiles (quota-metered); side-by-side profile comparison |
| 11 | **Backlink gap analysis** | Domains linking to ≥N competitors but not you, ranked by authority × topical relevance; the classic outreach shopping list |
| 12 | **Outreach opportunities** | Gap results + lost-link reclamation + unlinked brand mentions (reuse the footprint matcher against SERP/citation data — a Yanki-native source no pure link tool has) → exportable prospect lists with contact-page URLs. Full CRM explicitly out of scope |
| 13 | **Alerts** | New authoritative link, lost authoritative link, toxic spike, velocity anomaly, competitor gains — through the M4 alert engine (email/Slack/in-app), with M2 shipping a minimal email fallback if it lands first |
| 14 | **Historical changes** | Snapshot model: monthly profile aggregates retained indefinitely, link-level events 24 months (paid) — trends survive vendor churn |
| 15 | **Filtering** | Every list filterable/sortable: attribute, authority band, anchor class, TLD, language, first/last seen, status, toxicity band; saved filters |
| 16 | **Exports** | CSV/XLSX on every view; disavow export; scheduled export to email (report integration at M6) |
| 17 | **Reports** | Backlink section blocks (profile summary, new/lost, gap highlights) registered for the M6 white-label report builder; interim: a standalone per-project backlink summary page printable as PDF |

## 4. Data model (planning sketch)

```
backlink_sources(id, vendor, config, cost_tags…)            -- adapter registry
backlink_profiles(id, project_id, domain, snapshot_at, totals_json)   -- aggregates
backlinks(id, project_id, source_url, source_domain, target_url, anchor,
          attrs, first_seen, last_seen, vendor, vendor_metrics_json,
          verified_at?, status)                              -- current inventory
link_events(id, project_id, backlink_ref, kind[new|lost|changed], at, reason?)
referring_domain_rollups(project_id, domain, metrics…, period)
anchor_rollups(project_id, anchor_class, anchor, counts, period)
toxicity_assessments(backlink_ref, score, reasons_json, assessed_at)
competitor_link_targets(project_id, competitor_domain, tracked_since, quota_class)
gap_results / outreach_lists(project_id, computed_at, rows_json | rows table)
```

All rows org-scoped (M1); all vendor calls cost-tagged into the credit
ledger. Storage growth is the known hazard — link-level rows are capped per
plan (e.g. top-N by authority live in Postgres; full dumps go to object
storage as export artifacts), aggregates are forever.

## 5. Build stages (→ Phase 8 cards)

| Stage | Card | Contents |
|---|---|---|
| B1 | P8.1 | `BacklinkSource` protocol + mock adapter + fixtures; schema v1 (profiles, backlinks, events); $0 end-to-end under DRY_RUN |
| B2 | P8.2 | First licensed adapter (per A4 vendor decision) + cost tagging + quota enforcement (M1 credit service); initial import flow for one project |
| B3 | P8.3 | Inventory UI: backlinks/referring-domains/anchors views with filtering + exports |
| B4 | P8.4 | Monitoring: scheduled refresh, delta engine, new/lost views + events; liveness verifier for claimed losses |
| B5 | P8.5 | Metrics: authority (vendor + transparent Yanki Authority), velocity trends, history snapshots |
| B6 | P8.6 | Toxicity assessment + disavow export (advisory wording reviewed) |
| B7 | P8.7 | Competitor profiles + gap analysis + outreach lists (incl. unlinked-mention source) |
| B8 | P8.8 | Alerts + report blocks + methodology-page section; hardening/cost-soak; docs + ADRs |

Complexity: **M–L overall** (B1–B3 are straightforward CRUD-over-vendor;
B4–B7 carry the modeling risk). Each stage is one to two focused sessions
at recent velocity, decomposed further at build time.

## 6. Dependencies, risks, acceptance

**Dependencies:** M1 (org scoping, quotas, credit ledger, plan gates) ·
vendor contract + budget (**operator A4**) · scheduling primitive (M4's; B4
ships a minimal per-project cron if M4 hasn't landed — flagged as interim) ·
methodology page update (exists).

**Risks:** (1) *Vendor cost drift / ToS change* — the multi-vendor seam +
cost tags + per-plan caps are the mitigation; monthly COGS review in the
admin usage page. (2) *Data freshness disputes* ("Ahrefs shows a link you
don't") — provenance labels + liveness verification + honest "index
coverage differs" docs; never claim completeness. (3) *Storage growth* —
plan-capped link rows + aggregate-first retention (above). (4) *Toxicity
over-claiming* — advisory framing, reasons always shown, no auto-disavow.
(5) *Sequencing pressure* — backlinks before scheduling/alerts exist means
B4/B8 build minimal versions of both; accepted, recorded when it happens.

**Acceptance (M2 exit):** a project shows a populated backlink inventory
from the licensed vendor within its plan quota; new/lost events accrue
across ≥2 scheduled refreshes with a verified-lost example; anchors/
referring-domains/velocity/authority render with the documented formula;
gap analysis against ≥2 competitors produces an exportable list; toxicity
flags carry reasons and a valid disavow file exports; all spend visible in
the admin credit ledger; DRY_RUN suite green at $0; methodology page
documents the metrics.

**Explicitly not in M2:** owned crawling index · outreach email sending/CRM
· link-building marketplace · PR/HARO features · auto-disavow.
