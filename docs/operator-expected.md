# Operator Expected — everything only a human can do

*The single operator file. Maintained by the orchestrator; tick items as you
do them. Nothing here blocks local development — `make dev` + `make test`
work with zero keys and zero cost (DRY_RUN).*

Last updated: 2026-08-05, **session 21 close — the Admin Platform spine and
the Backlink backend.** Two things are yours, both small: **B8** (merge this
session's PR — it is what finally lands session 20's planning docs on `main`)
and **B9** (glance at one Tavily invoice and correct a pinned price). **B7 is
DONE and you closed it** — details below.

**What shipped, so you know what merging means.** Backend only; no UI card was
started, per your "skip ui issues". Admin Platform: tenancy
(organizations → workspaces → projects, every existing user given a personal
org), RBAC (ten roles, deny-by-default), the audit spine (append-only, with
credentials redacted before storage), and plans/quotas/credit ledger. Backlink
Intelligence: the vendor seam, a deterministic $0 mock, five tables, the delta
engine, Yanki Authority, toxicity + disavow, and gap/outreach analysis — then
the two joined, so every backlink import reserves quota before calling a
vendor and settles the real cost after.

**Merging changes almost nothing live**, and the exceptions are worth knowing.
Backlinks ship dark (`BACKLINKS_ENABLED=0`) with no vendor configured, so that
whole module is inert. Tenancy adds tables and backfills 3 personal orgs;
anonymous analyses are untouched. The one *visible* change is a fix: the
measured pipeline had been recording **$0 for every analysis** since PR #11 —
the cost was computed and then thrown away — so `CHECKER_DAILY_USD_CAP` could
never trip. It now records real cost, which means that cap becomes live for
the first time (relevant to **B3**, the checker go-live). Spend was never
uncapped, only invisible: the count caps were doing the bounding.

Earlier the same day — **session 21 open.**
**Good news first: B7 is DONE, and it was you who closed it.** This session
could verify it, because this checkout sits on the production VPS: the file
the live stack actually reads (`/home/aytek/deploy/yanki-mvp/deploy/.env`)
carries non-empty `OPEN_ROUTER_KEY` **and** `TAVILY_API_KEY`, the running
`yanki-prod-api-1` container has both in its environment, and — the check
that actually matters — **live analyses are completing**: the eight most
recent prod runs are all `done` (latest 2026-08-05 07:58 UTC), and the last
`failed` row predates the PR #11 merge. `DRY_RUN=0`, `GEO_MODE` is unset so
it takes the code default `measured`. Production is healthy on `a326159`
(`/healthz` → `{"status":"ok"}`). Nothing is expected from you on B7.

**One new thing is genuinely yours — B8, and it is small:** session 20's
entire planning set (roadmap, admin-panel-plan, backlink-intelligence-plan,
feature-parity, differentiators, architecture-target, ADR-33) **never reached
`main`**. It is one unmerged commit (`19d8236`) stranded on the branch
`backlinking`, with no PR ever opened — so for the last day `main` has had no
roadmap while two more PRs merged on top of it. This session merged `main`
into the work branch and carries those docs forward, so **reviewing and
merging this session's PR is what fixes it**. Also for your awareness, not
your action: **PRs #24 and #25 merged 2026-08-05 outside the session
process** (~5,800 lines of frontend — a Semrush-style app shell + nav,
AI-Visibility and Search-Visibility pages, the Site Audit UI), again with no
ADR, plan card or session log — recorded as tech-debt **#56**, as a schedule
item and not as blame. **A3 is still formally open**; this session proceeded
on its stated default ("proceed as written") because you asked it to continue
autonomously — say the word if that was wrong and the tenancy work reverses
cleanly. **A4 is unchanged and still blocks Phase 8 only** (not Phase 7).
A1, A2, B2–B5 are unchanged.

Earlier — 2026-08-05, **session 20 close — the re-planning session.**
Docs only; no code, no deploy, nothing flipped. Per your brief, the project
now has a **platform roadmap** ([roadmap.md](roadmap.md), milestones M1–M9)
built from your PDF (`docs/Yanki_Geo_Intelligence_Report.pdf`) and a full
repo + competitive analysis: **Admin Platform first (Phase 7), Backlink
Intelligence second (Phase 8)**, then parity → differentiators → enterprise.
New/updated docs: feature-parity, differentiators, admin-panel-plan,
backlink-intelligence-plan, architecture-target, roadmap, resume-prompt,
implementation-plan (Phases 7/8), ADR-33. Three things are yours before the
next build session: **A3** (ratify the roadmap — "proceed" is a complete
answer), **A4** (backlink data vendor + budget, needed before Phase 8, not
Phase 7), and **B7** — a real one, please read it: **PR #11 changed the live
pipeline's provider requirements, and prod may need two new keys in
`deploy/.env`.** Also for your awareness: PRs #4, #13, #23, #11 merged
2026-08-03/04 outside the session process; #23 and #11 carried no docs —
recorded as tech-debt #54/#55 with scheduled repayment, not as blame.
**A1 and A2 remain open and unchanged**; the checker go-live (P5.11) is
still yours and still independent of all of this.

Earlier — 2026-08-03, **session 17 close.** You answered **B6** — yes,
run it — and it is done: the SearXNG instance is standing in production and
**SERP visibility is ON**. `deploy/.env` on the server gained three lines
(`COMPOSE_PROFILES=serp`, `SERP_ENABLED=1`, `SERP_BASE_URL=http://searxng:8080`),
the instance is live-proven on the box (Salesforce 4/4, HubSpot 4/4, Baykar
3/4 on their own categories, ~0.5 s median per query), and — unlike session
16 — **this one does change the live site**: finished analyses now carry a
SERP number next to the GEO score wherever the search panel was measurable.
Work is on `feat/serp-instance`, awaiting your review; merging keeps the
committed compose stack in sync and (re)deploys the container. Be clear-eyed
about the cost: this stood up a **fifth container on a VPS shared with four
other production tenants**, a metasearch aggregator that is exactly the kind
of process that grows into whatever memory it is given — so it is capped hard
(**512 MiB**, 0.5 CPU, bounded logs) and measures **~150 MiB steady state**;
the box had **~3 GB free** when it went up. That leaves three genuinely new,
standing duties — watching it stays healthy, reading a non-empty
`unresponsive_engines` as normal rather than an outage, and knowing how to
switch it back off — all recorded under **B6**, now marked done.
**A1 and A2 remain open and still yours**, untouched by this work, which is
English-only too (`SERP_LANGUAGE=en` pinned, the same reason A2 stays parked).

Earlier — 2026-08-03, **session 16 close.** This session added **SERP
visibility** — whether the company also turns up in ordinary search results,
shown next to the AI-answer GEO score. The source is a **self-hostable SearXNG
instance** (open-source metasearch, AGPL-3.0) that you run and we read. It ships
**off by default** and stays completely dark until you both stand an instance up
and set two env vars, so this is the first session in a while where **merging
changes nothing on the live site** — no key, no visible behaviour change, no
forced decision. What it does add is one *optional* thing that is genuinely
yours: whether to run a SearXNG instance at all (**B6** below). Nothing breaks if
you never do — the GEO score is unaffected. Work is on `feat/serp-visibility`,
awaiting your review; merging still auto-deploys, and the deploy applies an
additive migration (one table + five nullable columns, all empty until you turn
it on). **A1 and A2 remain open and still yours**, untouched by this work — which
is English-only too, the SERP language pinned to `en`.

Earlier — 2026-08-01, **session 15 close.** Another pipeline-quality
session, again no ops work: `docs/pipeline-quality-plan.md` (discovery, KYC and
prompt quality, MVP → product) is implemented on
`feat/pipeline-quality-production-grade`, **PR open, awaiting your review**.
Nothing here needs a key, an env var or a decision from you — but **merging
auto-deploys to production**, and three things change visibly on the first live
day (session log §6): hallucinated products/competitors stop appearing in the
KYC card, a profile whose only topic signal was a placeholder now fails instead
of running, and prompts no longer name the brand they measure — which **lowers**
the score for any site whose keywords contained its own brand. That last one is
a correction: those questions were scoring the brand against itself. No new paid
call was added on any path. **A2 is still open and still yours** (Turkish steps
2b + 6); this work was language-neutral and left that decision untouched.

Earlier — 2026-07-28, **session 14 close.** That session was pipeline
quality work, not ops: five of the six steps in
`discovery-kyc-improvements.md` shipped on `feat/discovery-kyc-improvements`
(**[PR #10](https://github.com/Beyond-Kaira/yanki-mvp/pull/10), CI green —
awaiting your merge**). No key or env var moved and the checker is still dark,
but **merging that PR auto-deploys to production**, and it carries one visible
behaviour change: a crawl that used to return a meaningless-but-successful score
(empty company, or no topic signal) now **fails** with an honest message. That
is step 5's gate working as designed — expect a higher failure rate on the first
live day, not a regression.
**One new question for you: A2** (whether to revive two parked Turkish items) —
it does not block P5.11 or that merge, and "stay parked" is a complete answer.
Everything below this paragraph is unchanged from the session-13 close.

Earlier — 2026-07-10, **session 13 FINAL close (after five operator
follow-ups, all shipped same day; last-good `d6514ee`, CI green).**
The build is done: plan **43/44 ≈ 98%** — the only remaining card is
**P5.11: your go-live**. Beyond the six build tasks, this session also
delivered on your directives: the **Gemini prod-incident hotfix**
(live-proven: 4 real engines, $0.0253/analysis), **brand icons + logo
site-wide**, **growth-loop emails** (thank-you invites a first analysis;
kind-aware run-alert links; waitlist CTA on both results pages), the
**responses-table width fix**, the **"yanki" wordmark spelling**, and —
with your verified domain + new key — **emails now DELIVER to real
recipients** (proven both directions). The checker still answers 503
(dark) until B3. Signup mails are deduped by design: one thank-you per
address ever, 10 signups/IP/hour (your question — session log §11).
Next session = P5.11 at your pace: answer A1, do B2, then B3.

## A. Questions waiting for your answer

*Reply in chat or edit inline. "Keep defaults" is a complete answer for A1.*

- [ ] **A1. Checker go-live decisions** (the former item 13; due before
  P5.11 flips the checker public):
  - **Abuse thresholds** — in code: 10 checks/IP/hour, 20 fresh
    runs/brand/day, $5/day cost cap. *Default: keep.* → Answer: ______
  - **Email-gate strength** — single unverified email (max lead capture)
    vs verification / disposable-domain blocking / captcha.
    *Default: single unverified.* → Answer: ______
  - **The one free raw answer** — *default: first answer that mentions the
    brand.* → Answer: ______
- [ ] **A2. Discovery/KYC steps 2b + 6 — revive parked Turkish scope?**
  (added 2026-07-28, session 14; **not urgent, does not block P5.11**.)
  Five of the six steps in
  [discovery-kyc-improvements.md](discovery-kyc-improvements.md) shipped this
  session. Two did **not**, because both revive scope you parked on 2026-07-10
  ("the whole product ships English-only for now… revived only on the
  operator's word"), and that is your call, not engineering's:
  - **Step 2b — Turkish suffix-aware brand matching.** Today `Yankinin
    ürünleri` does *not* count as a mention of `Yanki`, so a Turkish answer
    that names the brand with a grammatical suffix scores as a miss. This is
    roadmap §2c's "Turkish suffix-aware brand/footprint matching" verbatim, and
    rule (b) of the skipped P5.8 card. Small change (~half a day) on top of what
    already shipped. *Default: stay parked.* → Answer: ______
  - **Step 6 — record the site's language** (`<html lang>` / ccTLD → a new
    `KYC.language` field). Changes **no** behaviour on its own; it is the
    missing input every localization effort needs, and it is the only step of
    the six that touches the `KYC` model. Approve it as "record it from now on",
    or decline it as premature. *Default: decline.* → Answer: ______
  - **One thing that already shipped and is worth knowing.** The dotted-`İ`
    fix (`İşbank` now matches `Isbank`) went in **ungated**, as part of the
    language-neutral half, on the grounds that it is a Unicode correctness bug
    — Python's `casefold()` turns `İ` into two characters, which corrupted
    match positions in *every* language — and the same change fixes `Nestlé`
    and `Škoda`. The P5.8 card lists it as a Turkish item, so flagging it: if
    you'd rather it were gated on language, say so and it is one module to
    change. → Objection? ______

- [ ] **A3. Ratify the platform roadmap (added 2026-08-05, session 20).**
  The milestone order in [roadmap.md](roadmap.md) — M1 Admin Platform → M2
  Backlink Intelligence → M3–M6 parity → M7 automation → M8 enterprise →
  M9 advanced AI — implements your re-planning brief. Phase 7 (P7.1,
  tenancy schema) starts on your word. *Default: proceed as written.*
  → Answer: ______
- [ ] **A4. Backlink data vendor + budget (added 2026-08-05, session 20;
  blocks Phase 8, not Phase 7).** The plan
  ([backlink-intelligence-plan.md](backlink-intelligence-plan.md)) licenses
  an index behind an adapter seam rather than crawling one. Needed from you
  before P8.2: which vendor to contract first (DataForSEO-class wholesale
  is the plan's default candidate; Majestic and Moz Links API are the named
  alternatives) and a monthly data budget so quotas and plan gates can be
  sized against real COGS. ToS review is part of the same decision.
  → Answer: ______

## B. Actions only you can do (in priority order)

- [ ] **B9. Check one Tavily invoice and correct the per-search price
  (added 2026-08-05, session 21; low urgency, no rush).** This session found
  that the live measured path recorded **no spend at all** — the pipeline
  computed each call's cost and then wrote a literal `0` into
  `responses.cost_usd`, so `CHECKER_DAILY_USD_CAP`, which is enforced by
  summing that column, could never trip. Fixed (`ed384a1`): every stage now
  reports its price and the row stores the total. One input is still a guess —
  **Tavily's per-search price**, pinned at `TAVILY_SEARCH_USD=0.008` and marked
  UNVERIFIED, because Tavily bills in plan-dependent credits nothing in the app
  can read. It is set high on purpose so a cap fails safe. When a real invoice
  arrives, divide by the search count and set the true value in `deploy/.env`
  (no redeploy needed beyond the usual restart). OpenRouter needs no such pin —
  it reports its own cost per call. Two things worth knowing rather than doing:
  spend on the live path has been **invisible, not uncapped** — the count caps
  (5/IP/hour, 100/day, 10 prompts/run) were doing the bounding all along; and
  the daily USD cap becomes genuinely live from this change, so factor it into
  the P5.11 go-live (**B3**).

- [ ] **B8. Review + merge this session's PR — it is what finally lands the
  session-20 planning docs on `main` (added 2026-08-05, session 21).**
  Session 20 wrote the whole roadmap set and committed it as `19d8236` on the
  branch **`backlinking`**; no PR was ever opened, so none of it is on `main`.
  Meanwhile `main` moved 12 commits ahead (PRs #24, #25). This session merged
  `origin/main` into the work branch `feat/p7.1-tenancy`, so its PR carries
  **both** the stranded planning docs and the Phase 7 work. Nothing is lost
  either way — the commit is safe on `origin/backlinking` — but until that PR
  merges, any agent starting from `main` alone still sees no roadmap. After it
  merges, `backlinking` can be deleted. As always, **merging auto-deploys**;
  this PR's runtime surface is additive and reversible (see the session log's
  deploy-impact note before you merge).

- [x] **B7. Verify prod `deploy/.env` against the PR #11 provider change —
  DONE 2026-08-05, verified in session 21.** Both keys are present in the
  file the live stack reads and in the running container, `DRY_RUN=0`,
  `GEO_MODE` unset (code default `measured`), and **live analyses complete**:
  the eight most recent prod rows are all `done` (latest 2026-08-05 07:58
  UTC); the last `failed` row is 2026-08-03 12:05 UTC, before PR #11 merged.
  The env file was last written 12:46–12:47 UTC and the stack recreated at
  12:49:07 UTC outside the CI deploy log — i.e. you pasted the keys and
  redeployed by hand. Nothing further is needed. Original text, for the
  record: PR #11 (merged 2026-08-04) rewired the
  pipeline's execute step: the default `GEO_MODE=measured` path calls
  **Tavily** (search) and **OpenRouter** (LLM), and with `DRY_RUN=0` the
  OpenRouter client **refuses to construct without `OPEN_ROUTER_KEY`** —
  meaning live analyses fail if the keys are absent. On the server check
  `deploy/.env` for `OPEN_ROUTER_KEY` and `TAVILY_API_KEY` (names per
  `deploy/.env.example`); either paste both keys (then redeploy), or set
  `GEO_MODE=simulated` (OpenRouter key still required), or park the live
  pipeline with `DRY_RUN=1` until you decide. A quick live check: submit
  one analysis on prod and see whether it completes. This session was
  docs-only and could not verify the server file — that is exactly why
  this item exists.
- [x] **B1. Resend sending domain — DONE 2026-07-10** (you verified
  `beyondkaira.com` and supplied a new key + sender). Prod now sends as
  `Yanki <aytek@beyondkaira.com>` (new key in gitignored `deploy/.env`,
  redeployed same day). Live-proven: a fresh waitlist signup delivered the
  thank-you to the joiner and the alert to `info@beyondkaira.com` with no
  errors. If you'd rather send from a different mailbox (e.g.
  `yanki@beyondkaira.com`), change `EMAIL_FROM` in `deploy/.env` and
  redeploy — the domain is what's verified, not the mailbox.
- [ ] **B2. Vendor ToS + pricing check for Gemini/Perplexity** (before
  P5.11 go-live) — **updated after the 2026-07-10 prod incident** (a live
  analysis failed; fixed same day, commit `7ff580f`): Google retired
  `gemini-2.5-flash` for new accounts, so the adapter now uses the rolling
  alias **`gemini-flash-lite-latest`**, and your free-tier key has **zero
  search-grounding quota** — Gemini answers are honestly labeled
  `:ungrounded` until you act. Your parts:
  (a) **Enable billing on your Google AI Studio project** if you want
  grounded (live web search) Gemini answers — after enabling, just tell
  the next session to redeploy; grounding re-activates automatically.
  (b) Verify current prices: flash-lite is pinned **UNVERIFIED** at
  $0.10/$0.40 per 1M in/out; Perplexity `sonar` $1/$1 (verified working
  live). `cost_usd` still undercounts per-request search fees — retune in
  P5.11's week-1 read.
  (c) The ToS sanity check on both vendors stands.
- [ ] **B3. P5.11 go-live itself stays yours** (after A1 + B2): flip
  `CHECKER_ENABLED=1` in `deploy/.env`, redeploy, supervise the live
  4-engine smoke. No agent will flip it.
- [ ] **B4. Rotate the Resend API key when convenient** — BOTH keys you
  used today were pasted into chat transcripts (the original and the
  2026-07-10 replacement `re_6ZpH…`); rotate in the dashboard, re-paste
  into `deploy/.env`, redeploy.
- [ ] **B5. (Optional) local browser deps, one root command:**
  `cd frontend && sudo npx playwright install-deps chromium` — enables
  local `make e2e` + native screenshots. Fully skippable: CI proves the
  e2e on every push; screenshots are done via dockerized Chrome.
- [x] **B6. (Optional) SERP visibility — SearXNG instance stood up. DONE
  2026-08-03** (you said yes; done for you). SERP visibility is now live in
  production (ADR-29). What shipped:
  - **A profile-gated compose service** (`searxng`) in **both**
    `docker-compose.prod.yml` and `docker-compose.yml`, behind the **`serp`
    profile** — it starts only because `deploy/.env` now sets
    `COMPOSE_PROFILES=serp`, which compose reads from the project-directory env
    file, so opting in cost **no change to `deployment.sh`**.
  - **Pinned image** `searxng/searxng:2026.8.1-8892414dc`, **capped hard**
    (`mem_limit: 512m`, `cpus: 0.5`, bounded json-file logs); ~150 MiB measured
    steady state.
  - **No published port in prod** — only `api`/`worker` reach it over the
    compose network at `http://searxng:8080`. Its limiter is off, which is safe
    *only because* there is no port; the two move together, never separately.
    (The dev compose does publish a loopback port, `YANKI_SEARXNG_PORT` default
    8144, for debugging.)
  - **Host-side, gitignored `deploy/searxng/settings.yml`** (it carries a real
    `secret_key`), created from the tracked `settings.example.yml` and
    **symlinked into the auto-deploy checkout** — exactly the arrangement
    `deploy/.env` already uses. Engines are narrowed to the four real
    web-search ones (`google cse`, `duckduckgo`, `brave`, `startpage`).
  - **Three lines added to `deploy/.env` on the server:**
    `COMPOSE_PROFILES=serp`, `SERP_ENABLED=1`,
    `SERP_BASE_URL=http://searxng:8080`.

  **Now standing duties on you (new this session):**
  - **Watch it stays healthy.** It is a fifth container on a box shared with
    four other production tenants. It is capped and `restart: unless-stopped`,
    but it is now yours to notice — a search aggregator is the kind of process
    that grows into whatever it is given, which is exactly why the cap exists.
  - **`unresponsive_engines` being non-empty is normal, not an outage.** Two of
    the four engines are usually refused from this egress IP, and *which* two
    varies per query (`brave`/`startpage` refused 8/8 from the host, yet a probe
    from inside the compose network had `brave` answering and `duckduckgo`
    refusing). Most stored rows will list refused engines; that is accurate
    reporting, weighed by `measurable` — though it does lean the score on
    `google cse` more than a four-engine panel suggests.
  - **To turn it back OFF:** remove `COMPOSE_PROFILES=serp` (stops the
    container) or set `SERP_ENABLED=0` (keeps the container running but records
    every `serp_*` column NULL — "not measured", never "measured zero"), then
    redeploy.
  - **Bumping the pinned image is licensed by the scheduled `upstream drift`
    job going green**, not by an upstream release notice. That job reruns the
    SERP suite against `searxng/searxng:latest`; green means the newer image
    still parses, red means leave the pin where it is.

## C. Done (compacted history)

- [x] Session 13: **Gemini + Perplexity keys pasted** (closes the old
  item 12) → P5.7 shipped same session (`40d8a34`). **Brandkit v2 decision**
  (old item 14) → P5.12 shipped (`d5abee7`), WCAG ratios recorded,
  before/after screenshots in the session log.
- [x] Sessions 1–12: KYC fix verified · $10 spend caps on Anthropic+OpenAI
  (plus code-side caps; blast radius doubly bounded — escape hatches:
  `ANALYSES_DAILY_CAP=0` or `DRY_RUN=1` + redeploy) · run-mode LIVE
  (session 8) · OpenAI billing proven ($0.0026/analysis) · Caddyfile
  committed in ams-pulse (`d538631`) · first deploy + rollback exercised
  (P4.2) · real Anthropic/OpenAI keys (P4.1) · GitHub + CI green
  (`aytekXR/yanki-mvp`) · DNS `yanki.beyondkaira.com → 161.97.172.146` ·
  real `POSTGRES_PASSWORD` in `deploy/.env`.
- [x] Turkish: **deferred to Later, whole product EN-only** (your
  2026-07-10 directive; P5.8/P5.9 skipped, revive on your word).

## Local-machine quirks (informational)

- **Ports 5432 and 8140 are taken on this host.** Dev stack is
  parameterized: `YANKI_DB_PORT=5434 YANKI_WEB_PORT=8240 make dev`
  (web → http://localhost:8240, api on 8141). **Prod** loopback binds are
  8142 (web) / 8143 (api) — the host nginx edge proxies to these (they also
  serve deploy health checks).
- **Node is v20 here; README recommends 22 LTS.** All green on 20 —
  upgrade optional.
- **Docker group membership may not apply to long-lived sessions** —
  prefix with `sg docker -c "…"` or use a fresh login shell.
