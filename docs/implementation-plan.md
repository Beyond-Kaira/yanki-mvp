# Yanki — Implementation Plan (engineering execution)

*Audience: the founder-orchestrator and the coding agents they dispatch. This is
the **how** and **when** of the build — the ticket breakdown, sequencing, file
ownership, and status. The **what/why** (product) lives in
[roadmap.md](roadmap.md); the **scope authority** is [02-mvp.md](02-mvp.md). This
file does not duplicate either — it links to them.*

Related: [architecture.md](architecture.md) (how it's built),
[design.md](design.md) (repo structure + ownership + ADR log),
[test-suite.md](test-suite.md) (how "done" is verified),
[frontend-brandkit.md](frontend-brandkit.md) (tokens + components).

---

## How to use this doc

- **Tasks are the unit of work.** Each is sized so one autonomous agent finishes
  it in a single focused session. IDs are stable (`P<phase>.<n>`); never renumber
  — mark `superseded` instead.
- **Every task carries:** Goal · Why now · Dependencies · Complexity (S/M/L) ·
  Deliverables (files) · Acceptance criteria · Status.
- **Status vocabulary:** `todo` · `in progress — session N` · `done` ·
  `blocked (<reason>)` · `superseded`.
- **Before starting a task**, read the linked contracts and confirm no other
  agent owns your files this session (see the ownership map in
  [design.md](design.md)). **Stay inside your ownership set** — touching another
  agent's files corrupts a parallel build.
- **Cross-cutting contracts are locked** (API shapes, DB fields, env vars, ports,
  dep lists). They live in the session master SPEC and are mirrored in
  [architecture.md](architecture.md). Deviate only minimally, and record the
  deviation in your session summary.
- **The project must always run.** Build and test each pipeline step behind
  `DRY_RUN=1` before wiring a real key. Nothing Phase-4+ starts until the Phase-3
  happy path renders a score.

### Current Priority

✅ **Session 1 (2026-07-09): Phase 0 → Phase 3 landed and verified in one
orchestrated pass.** The DRY_RUN stack boots and was driven end-to-end —
`POST` a URL → `202` → the six pipeline steps run → a GEO score renders
(`geo_score=0.6`, `total_responses=40` = 10 prompts × 4 mock engines); the
failure and `422` paths hold. A 5-dimension adversarial review pass confirmed
and fixed 16 findings (SSRF guard, footprint word boundaries, idempotent
re-runs, prod Dockerfile, deploy-script fixes) with the live smoke re-verified
afterwards. Default ports stay web `8140` / api `8141`, overridable via
`YANKI_WEB_PORT`/`YANKI_API_PORT`/`YANKI_DB_PORT`.

✅ **Session 2 (2026-07-09): the key-free CI + accessibility polish landed.**
P4.3 (CI hardening) and P4.5 (a11y audit) are done and P4.4's Playwright e2e job
is authored — but none of it has run on a real GitHub runner yet (there is still
no remote). Locally, `make lint`/`typecheck`/`test` are green (**64** backend
tests incl. real-Postgres `SKIP LOCKED` queue tests on `:5433`, **20** vitest
across 8 files) and a fresh DRY_RUN smoke re-verified the whole loop. See the
per-task notes below for exactly what was proven vs. authored-but-unproven.

✅ **Session 3 (2026-07-10): P4.6 landed — Phase 5 decomposed (planning only).**
The roadmap **Next** 2a slice (free public checker) is broken into 11
session-sized tasks — see **Phase 5** below (preamble, build gate, lanes, merge
risks, P5.1–P5.11). Produced by a 3-proposal / 3-judge / 3-lens
adversarial-verify orchestration; no code changed and `make test` stayed green
(64 backend + 20 frontend).

📣 **Post-close update (2026-07-10): the operator pushed to GitHub**
(`github.com/aytekXR/yanki-mvp`) **and the first-ever CI run executed: 4 of 5
jobs green on the first attempt** (backend / frontend / contract-drift /
secrets-gitleaks). The **e2e job is red** — it died at `npm ci`, before
Playwright: the job boots the bind-mounting compose stack first, the web
container (root) writes `frontend/node_modules` into the checkout, and the
runner user then gets `EACCES`. (Diagnosed in tech-debt item 2 at the time;
repaid session 4.)

✅ **Session 4 (2026-07-10): the CI proof completed — all five jobs green.**
The e2e failure's mechanism was confirmed and fixed: dockerd creates a missing
host-side anonymous-volume mountpoint (`frontend/node_modules`) as root when
the compose stack boots before `npm ci`; the job now installs frontend deps +
Playwright *before* the boot, so the runner-owned dir is reused and ownership
is preserved. Reproduced and the fixed order verified locally in a scratch
checkout before pushing. Run 29059944092: **5/5 green — the Playwright
happy-path spec executed for the first time anywhere, `1 passed (6.6s)`
(P4.4 done)**. A second push bumped the Node-20-deprecated action majors
(checkout v7, setup-node v6, setup-uv v7 — release notes checked against our
usage; setup-uv capped at v7 because v8 dropped floating major tags); run
29060093072 stayed **5/5 green** with the deprecation annotations cleared.
Tech-debt items 2–3 repaid (list renumbered; see tech-debt.md header).

✅ **Session 5 (2026-07-10): the last key-free task landed — `next lint` →
ESLint CLI (old tech-debt #10 repaid).** Gate check first: `deploy/.env`
still has empty keys, so P4.1 stayed blocked and the brief's fallback ran.
Minimal-risk diff (2 lines): the frontend `lint` script is now
`eslint . --ext .js,.jsx,.ts,.tsx --max-warnings 0` (the Next-16-blocking
`next lint` call is gone; ESLint 8.57 + `.eslintrc.json` deliberately kept —
no dependency or lockfile churn), plus `next-env.d.ts` added to
`ignorePatterns` (Next regenerates it; the official codemod ignores it too).
Coverage widened as a side effect: `eslint .` also lints `tests/`, `e2e/`,
and the root config files `next lint` never touched (verified 0 errors /
0 warnings). Verified by mirroring the CI frontend job locally (tsc, lint,
vitest 20/20, `next build` with its build-time lint still on) and on the
real runner. The flat-config + ESLint 9 move is deliberately deferred to the
Next 16 bump — new tech-debt #15 records the coupling (`--ext` and
`.eslintrc.json` both die under flat config; migrate together, manually —
the official codemod is buggy, vercel/next.js#85679).

✅ **Session 6 (2026-07-10): P4.1 done — the first LIVE run.** The operator
added keys mid-session and directed "use the cheapest models" — Anthropic
was already on Claude Haiku 4.5 (cheapest current Anthropic model); OpenAI
switched to `gpt-5-nano` ($0.05/$0.40, 3× cheaper input than gpt-4o-mini;
prices verified against the official pages, not memory). The live run
completed end-to-end in ~40s: real KYC for anthropic.com, `geo_score=0.2`,
**measured cost $0.0132/analysis** (Anthropic leg) ≈ 1% of the $49 plan at a
daily cadence — the NFR-1 margin holds with ~35× headroom. One blocker
discovered: the **OpenAI key has `insufficient_quota`** (billing) — its leg
(~+$0.002/analysis est.) gets recorded once the operator adds credits.
Full suite stayed green (64 backend + 20 frontend; ruff + mypy clean).

✅ **Session 7 (2026-07-10): P4.2 done — https://yanki.beyondkaira.com is
LIVE. The MVP plan (Phases 0–4) is 32/32 complete.** The operator said
"let's deploy"; a 4-agent pre-flight workflow reviewed the never-run deploy
path (verdict GO: 0 blockers, 36 checks passed — incl. validating the
concatenated Caddyfile inside the live Caddy container). First `make deploy`
caught one real bug: the prod web image build failed because
`ENV NODE_ENV=production` made `npm ci` omit devDependencies, so `next build`
couldn't transpile `next.config.ts` (fix: `npm ci --include=dev`, commit
3a84943). Second run deployed clean: build → migrate → healthy → last-good
recorded. A mock analysis ran end-to-end on prod (geo_score 0.6). The yanki
site block was appended to the shared Caddyfile, validated in-container,
Caddy **reloaded** (never restarted) — TLS issued immediately, and **all four
co-tenant sites matched their pre-reload baseline** (pulse 200 / apex 200 /
www 301 / ams 200). `make rollback` exercised clean (same-SHA path).
Tech-debt #1 repaid (list renumbered; old #8 rewritten as #7 — wiring now
proven, coupling remains). DRY_RUN=1 on prod by design for now (mock
pipeline, $0 — no rate limiting exists yet; going live-providers is an
operator flip).

✅ **Session 8 (2026-07-10): prod went LIVE-PROVIDERS + KYC card + OpenAI
leg recorded — the P4.1 residual is closed.** Operator directives: "run
mode: live-providers; KYC is very important, show it on the result page;
OpenAI is accessible now; Caddyfile pushed." Delivered: (1) an
implement+verify workflow replaced the raw-JSON KYC dump with a structured
`KycCard` (chips/dl idiom, hardened against missing fields, 5 new tests
incl. axe, all four CI-mirror checks green — commit d75c852); (2) prod
flipped to `DRY_RUN=0` and redeployed (last-good d75c852, co-tenants
re-verified); (3) first FULL live panel ran ON PROD via the public URL:
real KYC for anthropic.com, 10 Haiku 4.5 ($0.0135) + 10 `gpt-5-nano`
($0.0026) responses — **measured full-panel cost $0.0162/analysis ≈ 1% of
the $49 plan** (OpenAI quota pre-verified with one direct call; the
provider's 1024-token budget clears gpt-5-nano's reasoning overhead).
Consequence recorded honestly: tech-debt #2's "no rate limiting" risk is
now ACTIVE on a public URL — and P5.6 only covers the future checker
endpoint — so a new **P5.0** (minimal per-IP limit on `POST
/api/v1/analyses`, S) was added as the first Phase-5 task, and the operator
was asked to set provider-console spend caps meanwhile.

✅ **Session 9 (2026-07-10): P5.0 + P5.1 done — the live endpoint is
rate-limited and the checker API surface exists.** Both landed via
implement→adversarial-verify workflows, each deployed and verified on prod.
**P5.0** (commit 31061c0): migration 0002 (`analyses.ip_hash`),
`services/rate_limit.py`, 429 + `Retry-After` before any row/spend
(5/IP/hour + 100/day rolling; limit 0 = clean kill-switch, orchestrator
hardening after the verifier flagged a 500). Live acceptance on prod: one
real submit ($0.0201, ip_hash persisted) + 4 synthetic rows → 6th submit
**429, Retry-After 3587**; synthetic rows reset. With the measured cost,
the daily cap bounds worst-case abuse at **≈$1.62/day**. **P5.1** (commit
a8f0a06): migration 0003 (nullable `kind/brand/category/lang` + backfill,
`checker_submissions`), `POST /api/v1/checker` (202 `{id, submission_id}`,
normalized-triple 24h reuse, synthetic `checker://` url, ADR-19),
`POST /api/v1/checker/leads` (per-submission emails, no overwrite),
contract regenerated. **The verifier caught a critical bug empirically**:
the live worker would claim checker rows, fail crawling `checker://`, and
kill the reuse cache — fixed with a `claim_next` guard skipping
`kind='checker'` (**P5.2 must remove it** when the runner branches). Prod
smoke ($0): migration backfill verified, cache hit returned the same id
for `" YANKISMOKE "`→`yankismoke`, lead attached, worker skipped checker
rows (attempts=0); smoke rows deleted. Suite: 82 backend + 25 frontend,
ruff/mypy/tsc clean, CI green on P5.0 (P5.1 run pending at close).

✅ **Session 10 (2026-07-10): operator-directed KYC/prompt quality fix —
SPA sites now produce real profiles.** The operator reported KYC was
flat-wrong for beyondtech.com.tr (a defense/drone company profiled as
"generic IT services") and prompts read as mad-libs with no product
questions. Diagnosis: the site is an 890-byte JS-rendered SPA shell —
discovery fed KYC 21 chars of text; all real content (BAZNA/Tayron/Liftron,
TR+EN) lives in the 458KB JS bundle as string literals. Two workflow rounds
(commits `c8a1932`, `e120f56`): **discovery** harvests metadata everywhere,
prefers content-ful links (EN+TR keywords, diacritic-folded), and mines up
to 3 same-origin JS bundles (SSRF-guarded, 2MB cap) for prose literals —
non-ASCII-first ranking keeps framework noise out of the 20k cap
(verifier-caught live failure in round 1; round-2 verdict was "ship", zero
defects); **kyc** prompt forbids guessing, demands verbatim product names,
backfills empty locations from the ccTLD (com.tr → Türkiye); **prompts**
use category topics (keywords > short services > industry first-segment) in
question slots, never product model names, plus ≤count/4 brand-probe
prompts naming product+company, and a makers shape matching the operator's
example ("Who are the leading UAV manufacturers in Turkey?"). Live
before/after on prod for the same URL: KYC "IT solutions company" → real
defense profile with the full BAZNA line; score 0.0 → 0.1 (4/40 — engines
acknowledge the company on brand probes). 99 backend tests; session live
spend $0.045 across three acceptance runs. This consumed the session P5.2
was slated for; the checker ETA shifts ~1 session.

✅ **Session 11 (2026-07-10): operator confirmations + full-answer
expansion.** Operator confirmed items 0–2 (KYC fix verified; **$10 spend
caps set in both provider consoles** — blast radius now doubly bounded;
card design approved pending their brandkit integration). Their follow-up
shipped via workflow (commit `3106cae`, ship, zero defects): every response
row on the result page now expands to the **full verbatim LLM answer**
(collapsed by default, aria/axe-tested both states) — the first slice of
the "every raw answer one click away" wedge. Frontend-only; 31/31 tests;
deployed. Their KYC question answered on the record: profiles are
extracted live from the genuinely-fetched site text, nothing hardcoded
outside the DRY_RUN mock.

✅ **Session 12 (2026-07-10): P5.2 + P5.3 + P5.6 — the checker backend is
complete and deployed dark.** Three implement→adversarial-verify workflows
(each: 1 implementer + 3 lenses + bounded fix loop), one deploy at close.
**P5.2** (commit `d6e7253`, ship, 0 blocking): checker rows run all six
steps with zero HTTP — seed-string discovery, KYC as-is, fixed
`checker-en-v1` 12-prompt set (`checker_prompts.generate(kyc, lang)`,
category-question idiom, never names the brand — the checker measures
*unprompted* visibility; unwired langs fall back to EN until P5.8);
`_write_cache` upsert (PG-gated race test); `claim_next` guard removed
(debt #6 + #19 repaid, ADR-20). **P5.3** (commit `c5e4f6d`, ship after one
fix round — the heuristic lens caught possessive brand forms like "Nike's"
escaping exclusion, fixed pre-merge): pure read-time
`services/checker_summary.py` (ADR-21) → nullable checker-only
`engine_presence` + `competitors_appeared` in `ResultOut`; additive
contract regen. **P5.6** (commit `7542751`, ship after one fix round;
abuse-bypass lens probed XFF spoofing/counter bypass/guard ordering):
default-OFF `CHECKER_ENABLED` kill-switch (parked 503), per-IP 10/h +
per-brand 20/day 429s, rolling-24h $5 cost cap, salted `ip_hash` on
submissions; rejected submits record nothing; $0 cache hits exempt (debt
#21 repaid, ADR-22). Suite grew 113 → 146 backend tests; CI 5/5 green;
deployed (last-good `7542751`), co-tenants byte-identical, live-verified at
$0: fresh checker submit → 503 "not open yet" + zero rows, MVP results
unchanged with the new fields `null`. One workflow failure recovered: the
P5.3 implementer finished but died emitting its structured report
(oversized fields); resumed with a report-reconstruction stage —
implementation was intact, nothing redone.

🔄 **Post-close operator directives (2026-07-10, same day):** (1) **the
product is English-only** — P5.8/P5.9 skipped, Turkish moved to roadmap
Later; (2) **Gemini/Perplexity key FIELDS staged** in `deploy/.env` +
`.env.example` (operator pastes keys; inert until P5.7); (3) **brandkit v2
adoption un-parked and prioritized** — new card **P5.12**, which jumps
ahead of P5.4 so the checker UI is built once on the new tokens.

🏁 **Session 13 (2026-07-10, #11 today) finished the entire build:** P5.7
(`40d8a34`), P5.12 (`d5abee7`), P5.4+P5.5 (`a4dbdab`), **P5.13 — NEW
operator-directed card, waitlist + Resend emails** (`c521931`), P5.10
(`93aa34a` + build fix `643e0ee`), all CI-green and deployed dark at
session close. Full detail: `sessions/2026-07-10-11.md`.

🔍 **Session 19 (2026-08-03): P6.1 — account screens + the browser session
layer, in review.** The first slice of roadmap **§2d** (accounts), on
`feat/auth-screens` /
[PR #13](https://github.com/Beyond-Kaira/yanki-mvp/pull/13): sign up, log in,
log out, a header that knows who you are, and `lib/session.ts` +
`lib/api.ts` holding the access token in memory and rotating the httpOnly
refresh cookie behind it (**ADR-32**). PR #9 landed the endpoints behind it and
is recorded below as P6.0. The review returned **changes requested** (9 items)
and this session answered all of them: the password-reset flow and the terms
checkbox were **removed** rather than shipped (tech-debt #49, #50), the
cross-tab refresh race is closed with a Web Lock, and the three untested claims
the reviewer found — the 401 replay, the field-error announcement, the header's
anonymous branch — are now pinned by tests that were each confirmed to fail
without their fix. Frontend 122 passed across 26 files; tsc + eslint clean.
Merged against `main` twice as `main` moved 27 commits across the same session
— first against **P5.15**, then against **P5.16–P5.18** (SERP visibility, the
SearXNG instance, and two fixes + the SEO audit) — no code conflict either
time, two rounds of doc renumbering (this entry, ADR, tech-debt; see
`sessions/2026-08-03-04.md` §§8–9 for both). Full detail:
`sessions/2026-08-03-04.md`.

✅ **Session 14 (2026-07-28): P5.14 — discovery + KYC input quality**
(`cf28cbc`, `f25462d`, `8ce7356`, `c74ccd3`, `8337045`, `684108a` on
`feat/discovery-kyc-improvements`, **[PR #10](https://github.com/Beyond-Kaira/yanki-mvp/pull/10),
CI green**). Five of the
six steps in `discovery-kyc-improvements.md`: JSON-LD extraction, diacritic +
hyphen tolerance in footprint matching, a free KYC parse repair plus one
bounded retry, a Content-Type/size guard on page fetches, and a gate that
refuses the ≤60-call `execute` fan-out on a profile with no company or no
topic. ADR-26. **Steps 2b and 6 not built — operator decision A2.** Zero
contract drift. Full detail: `sessions/2026-07-28-02.md`.

✅ **Session 15 (2026-08-01): P5.15 — pipeline quality, MVP → product**
(branch `feat/pipeline-quality-production-grade`). The plan is
[`pipeline-quality-plan.md`](pipeline-quality-plan.md) and all three of its
workstreams shipped: **discovery** (meta-charset decoding, binary sniffing,
one homepage retry, scored link selection, cross-page boilerplate removal,
per-page budget, tighter SPA literal filtering), **KYC** (`sanitize.py` — one
normalized key for dedupe/grounding/leak detection; per-field sanitation;
grounding of products/competitors/model aliases against the crawl; the new
`category` + `use_cases` fields; a repair-prompted retry; a junk-aware
usability gate), and **prompts** (typed + filtered topic pool, kind- and
number-aware phrasing, full topic × shape rotation, and a hard invariant that
no scored question names the brand). ADR-27. Zero contract drift, no new paid
call, `checker_prompts.VERSION` unchanged. Backend 321 passed / 3 skipped,
frontend 70 passed. Full detail: `sessions/2026-08-01-01.md`.

✅ **Session 16 (2026-08-03): P5.16 — SERP visibility from an open-source
metasearch instance** (branch `feat/serp-visibility`). Yanki now measures the
*organic* search surface next to the AI-answer GEO score: a self-hostable
**SearXNG** instance (AGPL-3.0) read over its JSON API tells us whether the
company also shows up in ordinary results for brand-free buyer queries — the one
place in the pipeline that can see a company the LLM panel never names. Shipped
whole and **inside the existing footprint step** (no seventh step): the source
adapter (`serp/` — one `SerpSource` protocol, SearXNG + deterministic mock +
registry), the pipeline pass (`serp_visibility.py`, brand-free queries reusing
ADR-27's leak filter), persistence (`SerpCheck` + five nullable `serp_*` columns,
migration `0007`), the API contract (a nullable `serp` object), the UI
(`SerpVisibility` on both results pages), the tests, and a **new `SERP` CI
workflow** (real-SearXNG integration, scheduled upstream-drift, alembic up **and**
down on Postgres, one whole analysis through the DRY_RUN stack). ADR-28. **Off by
default** (`SERP_ENABLED=False`) — nothing changes for an existing deployment
until an operator turns it on and stands up an instance; **Google AI Overviews
itself stays open** (no $0 source). One real contract diff (`openapi.json` +
`types.ts`); `checker_methodology.json` unchanged. Backend 384 passed / 7 skipped
(the SERP integration tier, which needs a live instance), frontend 79 passed. Full detail:
`sessions/2026-08-03-01.md`.

✅ **Session 17 (2026-08-03): P5.17 — the SearXNG instance stood up, SERP live
in production** (branch `feat/serp-instance`). The operator decision ADR-28
deferred (operator-expected **B6**) was executed the same day: turn SERP on.
This is an **infrastructure change, not a feature change** — no pipeline,
provider, scoring or UI code moved. The instance is now a **profile-gated
compose service** in both the prod and dev compose files, behind the `serp`
profile, which compose reads from `deploy/.env`'s `COMPOSE_PROFILES`, so
`deployment.sh` is untouched: image pinned `searxng/searxng:2026.8.1-8892414dc`,
capped at `mem_limit: 512m` / `cpus: 0.5` with bounded json-file logs (measured
~105–150 MiB steady state on the shared VPS). **Prod publishes no port** — only
`api` and `worker` reach it at `http://searxng:8080`, which is exactly what lets
its limiter stay off — while dev publishes a loopback port for debugging.
`settings.example.yml` is tracked (the four real web-search engines kept, the
six default widget engines dropped); the real `settings.yml` lives on the host,
gitignored and symlinked into the auto-deploy checkout, exactly as `deploy/.env`
already is. The host `deploy/.env` gained three lines (`COMPOSE_PROFILES=serp`,
`SERP_ENABLED=1`, `SERP_BASE_URL=http://searxng:8080`). ADR-29. Measured live
against real results: Salesforce 4/4, HubSpot 4/4, Baykar 3/4 on their own
categories, ~0.5 s median per query; `unresponsive_engines` is non-empty on most
stored rows because two of the four engines refuse this egress IP — accurate
reporting, not a fault. Two new tech-debt items, **#43** (DRY_RUN forces the
mock SERP source) and **#44** (two of four engines refused per query, so the
score leans on `google cse`). Full detail: `sessions/2026-08-03-02.md`.

📐 **Session 20 (2026-08-05): the re-planning session — the platform roadmap
adopted (ADR-33). Docs only; no code changed.** The operator's brief:
analyze the repo + the planning baseline
(`docs/Yanki_Geo_Intelligence_Report.pdf`, Aug 2026), establish competitive
feature parity, and re-plan around a fixed implementation order — **Admin
Panel first, Backlink Intelligence second, remaining parity third,
differentiators fourth, enterprise last.** Delivered: the milestone roadmap
rewrite ([roadmap.md](roadmap.md), M1–M9), the parity analysis
([feature-parity.md](feature-parity.md)), the differentiation proposal
([differentiators.md](differentiators.md)), the M1 admin plan
([admin-panel-plan.md](admin-panel-plan.md) → **Phase 7** below), the M2
backlink plan ([backlink-intelligence-plan.md](backlink-intelligence-plan.md)
→ **Phase 8** below), the target architecture
([architecture-target.md](architecture-target.md)), and the updated
orchestrator brief ([resume-prompt.md](resume-prompt.md)). The session also
recorded that four PRs merged 2026-08-03/04 outside the session process —
**#4, #13 (P6.1 is therefore MERGED), #23 (Site Audit backend), #11 (the
measured/simulated GEO pivot: Tavily + OpenRouter, `geo_records`,
interventions, reliability)** — the last two with no ADR/plan/session docs:
tech-debt **#54/#55**, and a possibly production-affecting key requirement
flagged as operator item **B7**. Full log: `sessions/2026-08-05-01.md`.

✅ **Session 21 (2026-08-05): Phase 7 opened and Phase 8's backend landed.**
**P7.1 done** (tenancy: organizations/workspaces/memberships/projects,
personal-org backfill, fail-closed org scoping — ADR-35) and the **Phase 8
backlink backend done** (seam + deterministic mock + five tables + delta
engine + Yanki Authority + toxicity/disavow + gap/unlinked-mentions —
ADR-36), both behind flags that default off. Also this session: the
retroactive **ADR-34** for PR #11 (repaying half of tech-debt #54), a
**live cost-recording fix** (the measured path wrote `cost_usd=0` for a week,
so the daily USD cap could never trip), and an **eight-index model/migration
drift** repaired before it could make an autogenerated migration drop
production indexes. Operator **B7 verified and closed**. Suite: 488 → **578
backend**. Full log: `sessions/2026-08-05-02.md`.

✅ **Session 22 (2026-08-05): the Admin Panel became a product surface.**
**P7.4 done** — `/admin` is now a named **Admin Panel** section with three
tabs, and the three things an administrator could not previously do all work:
**invite** somebody (hashed single-use expiring tokens, resend-rotates, a
public accept flow that creates the account and signs them in — ADR-37),
**remove** a seat without deleting the person, and **read the audit log**
(filter/search/sort/page, per-record history, before/after diffs). P7.3 closed
its three real gaps in the same pass: request id and hashed IP now actually
land on every event (ADR-39), auth events are attributed to an organization so
the sign-in trail is visible at all, and the trail is tamper-evident via a
per-row hash plus a Postgres trigger refusing UPDATE/DELETE (ADR-38). CI gained
a scoped formatting gate (ADR-40) and named gates for migrations, authorization
rules and Admin Panel behaviour. Suite: 752 → **811 backend** on the hermetic
SQLite run (**821 passed / 7 skipped** with `TEST_DATABASE_URL` set, which is
what `make test` does), and 232 → **277 frontend** across 51 files. Full log:
`sessions/2026-08-05-03.md`.

➡️ **Next up: P7.5 (auth completion — password reset #49, MFA, session
management) then P7.6 (plans/quotas/credit ledger).** P7.6 unblocks Phase 8's
metering; P8.4's residual (liveness verifier + scheduled refresh) needs the
worker wiring. The prioritized queue across every phase now lives in
[backlog.md](backlog.md). **P5.11 (checker go-live) stays operator-gated and
independent** — its blockers are unchanged: A1 decisions, A2, B2 vendor
ToS/pricing check, then the `CHECKER_ENABLED=1` flip + live smoke + week-1 cost
read.

### Readiness snapshot (updated at each session close)

Last updated: 2026-08-05 (**session 22 close**).

**Measured at session 22 close, on branch `feat/admin-panel-invitations-audit`:**

| Metric | Value | How it was obtained |
|---|---|---|
| Backend suite (`make test` path, Postgres) | **835 passed, 7 skipped** | `TEST_DATABASE_URL=…` + `uv run pytest` |
| Backend suite (default, hermetic SQLite) | **820 passed, 22 skipped** | `uv run pytest` — the extra 15 skips are the three Postgres-only modules |
| Frontend suite | **281 passed, 51 files** | `npm test -- --run` |
| End-to-end | **31 Playwright tests** | against a live API + web pair on a migrated Postgres |
| Migrations | up clean · **zero model drift** · down reverses | real Postgres 16 |

**Production is NOT on this branch.** Prod runs `yanki-api:f4c33e8` at alembic
`0017_user_status`; this branch adds `0018` and has never been pushed or
merged. The session-21 line below said prod was on `a326159`; that is
superseded — `f4c33e8` is the tip of `main` and what is deployed.

Every count *below this line* is the number that was true at the session it
describes — historical, not current. Treat any figure in the bullets that
follows (146/31, 170/65, 488/205) as an archive of its own moment, never as a
claim about today. Earlier — 2026-08-05 (session 21 close): 488 backend
(7 skipped) + 205 frontend across 41 files; prod healthy on `a326159` with real
measured analyses completing (`sessions/2026-08-05-02.md` §1.1). Earlier —
2026-07-10 (session 13 close —
P5.4, P5.5, P5.7, P5.10, P5.12, P5.13 all shipped and deployed dark; the build
phase of the plan is complete).

- **MVP plan completion (Phases 0–4): 32 / 32 tasks = 100%, all residuals
  closed.** Phases 0–3: 26/26. Phase 4: 6/6, and session 8 closed P4.1's
  last residual (the OpenAI cost leg, measured live on prod). The KYC card
  and the live-mode flip are operator-directed polish/ops inside completed
  surfaces, not new plan tasks.
- **Phase 5 (post-MVP checker): 11 / 12 built** — everything except the
  operator-gated P5.11. Session 13 shipped the remaining six build cards:
  P5.7 (real Gemini + Perplexity), P5.12 (brandkit v2), P5.4/P5.5 (checker
  frontend + email gate), **P5.13 (waitlist + Resend emails — NEW card,
  operator directive mid-session)**, P5.10 (methodology page). The full
  checker vertical runs end-to-end dark; the waitlist + run-alert emails
  are live-in-code (delivery pending the operator's Resend domain
  verification). **The enlarged plan stands at 43 / 44 ≈ 98%** (P5.13
  raised the count 43 → 44; only P5.11 remains and it is the operator's).
- **Production readiness: ~98%** (definition unchanged — this metric is the
  LIVE MVP product; the checker is intentionally unreleased until P5.11).
  Code, tests (**146 backend + 31 frontend**), docs, CI (5/5 green), secret
  scanning, accessibility, deploy/rollback exercised, TLS via the shared
  Caddy — the product runs **fully live in production**: real Anthropic +
  OpenAI panel at a measured **$0.0162/analysis ≈ 1% of the $49 plan**
  (NFR-1 headroom ~35×), behind P5.0 rate limiting (5/IP/hour + 100/day →
  worst-case abuse ≈$1.62/day) **plus the operator's $10 console caps on
  both providers** (session 11). Tests now **170 backend + 65 frontend**.
  The missing ~2%, in priority order: KYC-cost persistence + adapter
  contract tests (debt #1); multi-stage prod web image (debt #18);
  XFF-spoofable per-IP limits are accepted posture on all three public
  write endpoints (global/daily caps are the backstop; the waitlist adds
  one more such endpoint — debt #24). Gemini/Perplexity are REAL as of
  P5.7 (session 13) but their pinned prices are unverified and `cost_usd`
  undercounts search fees until P5.11's retune (debt #23).
- **On track vs. original plan: yes — MVP scope untouched; TWO
  operator-directed Phase-5 scope changes** (both 2026-07-10): post-session-12
  **Turkish out / brandkit v2 in**, and mid-session-13 **P5.13 added**
  (waitlist + Resend email notifications — net count 43 → 44).
  Historical note from the first change: P5.8/P5.9 skipped (whole product
  English-only; Turkish → roadmap Later, revived only on the operator's
  word — this consciously supersedes the draft's "Turkish at checker launch"
  mandate and roadmap 2c, recorded there too); P5.12 (brandkit v2 UI
  refactor) added ahead of P5.4 — the operator un-parked their own item 14.
  Net effect on the count: 44 → 43 tasks. **Session-12 sequencing change
  (order, not scope): P5.6 pulled ahead of P5.4/P5.5** — the plan explicitly
  allows it ("P5.6 … can run any time") and the session-9 brief recommended
  it: hardening landed in the same session that made checker rows runnable,
  so prod never had a runnable-but-unthrottled checker.
  **Session-6 operator-driven change (models, not scope): "use the cheapest
  models"** — OpenAI provider switched `gpt-4o-mini` → `gpt-5-nano`
  (Anthropic already on Haiku 4.5, the cheapest); P4.1 then ran live with an
  Anthropic-only panel because the OpenAI key lacks quota. Session 5 executed
  exactly the no-keys branch of the session-4 brief (the ESLint CLI fallback,
  old debt #10, since repaid). **One session-5 post-close operator-driven TARGET change (not
  scope):** the deploy is now
  `yanki.beyondkaira.com` on the shared VPS the dev host runs on, co-tenant
  with live sites (was `test.beyondkaira.com`); the P4.2 card, deploy
  configs, and operator checklist were updated in the same commit
  (`b32de42`) and the DNS prerequisite is already met. A `brandkit/` v2
  package also landed in the repo (operator-dropped); **its adoption is
  deliberately skipped for now** (operator call, 2026-07-10) — v1 tokens
  stay live. Prior recorded deviations stand: P4.3/P4.5 before P4.1
  (key-blocked fallback), P4.3 without a `.gitleaks.toml`.

### Agent lanes (parallelism map)

The session runs these lanes in parallel; the merge risks are the shared
contracts between them.

| Lane | Owns | Phase-1/2/3 tasks |
|---|---|---|
| **backend-spine** | `backend/` (config, db, api, jobs, services, worker, alembic, `tests/{conftest,test_api,test_queue,test_queue_postgres}.py`, `pyproject.toml`, `Dockerfile`) | P1.1–P1.6, P2.10a |
| **pipeline** | `backend/app/pipeline/**`, `backend/app/providers/**`, `backend/tests/pipeline/**` | P2.1–P2.9, P2.10b |
| **frontend** | `frontend/**` | P1.7, P3.1–P3.5 |
| **infra** | `Makefile`, `deploy/**`, `scripts/**`, `.github/**`, `.gitignore`, `CONTRIBUTING.md`, `SECURITY.md`, README link fixes | P0.2, P1.8, P4.2–P4.4 |
| **docs** | `docs/**` (one file per agent) | P0.3 |

**Shared-contract merge risks (coordinate before editing):**
- The **API envelope** (`GET /api/v1/analyses/{id}`) binds backend-spine ↔
  frontend. It is generated into `shared/contracts/openapi.json` →
  `frontend/lib/types.ts` by `make gen-types` (P3.1) — never hand-edit those; the
  frontend imports through the hand-maintained `frontend/lib/contracts.ts` seam.
- The **`KYC` / `PromptSpec` / `ProviderResult`** shapes bind pipeline ↔
  backend-spine (the worker calls the pipeline).
- **Config env vars** bind all lanes; the locked list lives in
  [architecture.md](architecture.md) and `deploy/.env.example`.
- **DB schema** is owned by backend-spine's Alembic migration; pipeline reads/
  writes those tables via the models but may not alter the migration.

---

## Phase 0 — Repository sanity

Goal: a clean, documented, ignorable-noise-free repo a new agent can navigate.

### P0.1 — Git init + baseline commit
- **Goal:** repo under version control with an initial baseline.
- **Why now:** every later task needs a repo to branch from.
- **Dependencies:** none.
- **Complexity:** S
- **Deliverables:** initialized `.git`, baseline commit of existing docs.
- **Acceptance:** `git log` shows a baseline commit; tree is clean.
- **Status:** done

### P0.2 — .gitignore + README link/consistency fixes
- **Goal:** ignore build/venv/node/env noise; fix README doc links (README points
  at `docs/mvp.md` but the file is `docs/02-mvp.md`) and confirm the Make-target
  and port tables match the SPEC.
- **Why now:** stops secrets/artifacts leaking into commits and stops the front
  door pointing at 404s.
- **Dependencies:** P0.1.
- **Complexity:** S
- **Deliverables:** `.gitignore` (Python, Node, env files, `.venv`, `__pycache__`,
  `node_modules`, `.next`, coverage, `deploy/.env`), README link fixes.
- **Acceptance:** `git status` is clean after a build; every README doc link
  resolves to an existing file; no `deploy/.env` is trackable.
- **Status:** done (session 1)

### P0.3 — Author the doc set
- **Goal:** author/refresh the docs so no doc drifts from the planned build:
  `design.md`, `architecture.md`, `roadmap.md`, `test-suite.md`, this
  `implementation-plan.md`; fill empty placeholders (`session-rules.md`,
  `agent-workflows.md`) or delete them.
- **Why now:** docs are the shared brain across short, context-limited sessions.
- **Dependencies:** the locked SPEC.
- **Complexity:** M
- **Deliverables:** the docs above (one agent per file).
- **Acceptance:** every doc cross-links correctly; no empty non-placeholder files
  remain; scope authority and contracts are consistent across docs.
- **Status:** done (session 1)

---

## Phase 1 — Foundations (the spine that everything hangs on)

Goal: an empty-but-running stack — api answers `/healthz`, worker polls an empty
queue, frontend renders a shell, `make dev` boots all four services. No pipeline
logic yet.

### P1.1 — Backend config
- **Goal:** `app/config.py` — pydantic-settings `Settings` reading the locked env
  vars (`DATABASE_URL`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DRY_RUN`=true,
  `PROMPT_COUNT`=10, `PANEL_ENGINES`, `MAX_RESPONSES_PER_JOB`=60,
  `WORKER_POLL_SECONDS`=2, `STALE_CLAIM_SECONDS`=300) with the SPEC defaults.
- **Why now:** every other backend module imports settings.
- **Dependencies:** `pyproject.toml` deps present.
- **Complexity:** S
- **Deliverables:** `backend/app/config.py`, `backend/app/__init__.py`.
- **Acceptance:** importing `settings` with no env set yields the documented
  defaults; `DRY_RUN` defaults **true** (safe by default).
- **Status:** done (session 1)

### P1.2 — DB base, models, session
- **Goal:** SQLAlchemy 2.0 models for `analyses`, `prompts`, `responses`,
  `llm_cache` per the locked schema; session factory; SQLite-compatible column
  choices (so unit tests run in-memory — see [test-suite.md](test-suite.md) §3.3).
- **Why now:** the queue, services, and pipeline all read/write these tables.
- **Dependencies:** P1.1.
- **Complexity:** M
- **Deliverables:** `backend/app/db/{base.py,models.py,session.py}`.
- **Acceptance:** models create cleanly on both SQLite and Postgres; UUID pks
  default to `uuid4`; timestamps are timezone-aware.
- **Status:** done (session 1)

### P1.3 — Alembic initial migration
- **Goal:** one migration creating all four tables + the `llm_cache.cache_key`
  unique index.
- **Why now:** `make migrate` and the deploy flow need a real schema.
- **Dependencies:** P1.2.
- **Complexity:** S
- **Deliverables:** `backend/alembic/**` (env + one revision).
- **Acceptance:** `alembic upgrade head` on a fresh Postgres creates the four
  tables; `downgrade base` drops them.
- **Status:** done (session 1)

### P1.4 — Postgres-as-queue
- **Goal:** `app/jobs/queue.py` — claim one job in a single transaction
  (`status='queued' OR (running AND claimed_at < now()-STALE_CLAIM_SECONDS)`,
  `ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED`), set `running`,
  `claimed_at=now()`, `attempts+=1`; `attempts>3 → failed`; a heartbeat helper to
  bump `claimed_at` between steps.
- **Why now:** the worker's correctness (NFR-3: never lose or double-run) lives
  here.
- **Dependencies:** P1.2.
- **Complexity:** M
- **Deliverables:** `backend/app/jobs/queue.py`.
- **Acceptance:** two concurrent claimers never grab the same row; a stale
  `running` row is reclaimed; `attempts>3` flips to `failed` with
  `error='max retries exceeded'`.
- **Status:** done (session 1)

### P1.5 — API layer + service glue
- **Goal:** `app/api/{main,routes,schemas}.py` + `app/services/analyses.py`
  implementing the locked contract: `GET /healthz`; `POST /api/v1/analyses`
  (valid → **202** `{id}`, invalid → **422**); `GET /api/v1/analyses/{id}` (full
  envelope with `result` **always present**, inner fields null until produced,
  unknown id → 404). Progress/step mapping per SPEC.
- **Why now:** it is the FE/BE contract surface and the entry point for the whole
  loop (FR-1, FR-2, FR-7).
- **Dependencies:** P1.2, P1.4.
- **Complexity:** M
- **Deliverables:** `backend/app/api/{main.py,routes.py,schemas.py}`,
  `backend/app/services/analyses.py`.
- **Acceptance:** matches the API contract exactly (see
  [architecture.md](architecture.md)); `app.openapi()` is exportable for
  `make gen-types`.
- **Status:** done (session 1)

### P1.6 — Worker skeleton
- **Goal:** `app/worker.py` — `while True` loop: claim a job (P1.4), run the
  pipeline (stubbed call for now — real steps land in P2.9), `time.sleep(POLL)`;
  on any exception mark `failed` with `str(exc)` truncated to 500 chars, partial
  rows kept.
- **Why now:** proves the queue drains; P2.9 fills in the real pipeline call.
- **Dependencies:** P1.4, P1.5.
- **Complexity:** S
- **Deliverables:** `backend/app/worker.py`.
- **Acceptance:** worker starts, claims a queued row, marks it `running` then
  `done` (stub), sleeps, repeats; a raised exception marks the job `failed`
  without crashing the loop.
- **Status:** done (session 1)

### P1.7 — Frontend scaffold + brand tokens
- **Goal:** Next.js 15 App Router + TS + Tailwind scaffold; copy the
  [frontend-brandkit.md](frontend-brandkit.md) §2 tokens into the Tailwind config;
  `next.config` `rewrites()` proxying `/api/:path*` and `/healthz` to
  `API_ORIGIN` (default `http://localhost:8141`) so there is **no CORS** and FE
  fetches relative paths only.
- **Why now:** the three screens (P3.x) need a themed shell and the proxy.
- **Dependencies:** none (contract-only dependency on the API shape).
- **Complexity:** M
- **Deliverables:** `frontend/` scaffold, `tailwind.config`, `next.config`,
  `package.json` with the locked deps.
- **Acceptance:** `npm run dev` serves a themed placeholder on `:8140`;
  `/healthz` proxies to the api; brand tokens resolve in Tailwind classes.
- **Status:** done (session 1)

### P1.8 — Compose + Makefile + Dockerfile + env example
- **Goal:** the single control panel. `deploy/docker-compose.yml` (db + api +
  worker + web, bind-mount hot reload); one backend `Dockerfile`
  (`python:3.12-slim` + `uv sync`, `CMD uvicorn app.api.main:app`) run as both api
  and worker; `Makefile` targets per the README contract; `deploy/.env.example`
  (all config vars + `POSTGRES_PASSWORD`, `DRY_RUN=1` default, commented, **no
  real keys**).
- **Why now:** `make dev` is the definition-of-done boot command.
- **Dependencies:** P1.1–P1.7 (services to compose).
- **Complexity:** M
- **Deliverables:** `deploy/docker-compose.yml`, `backend/Dockerfile`, `Makefile`,
  `deploy/.env.example`, `scripts/` bootstrap helpers.
- **Acceptance:** `make dev` boots all four services with hot reload; `make help`
  lists every target in the README table; `make migrate` runs against the db
  container.
- **Status:** done (session 1)

---

## Phase 2 — Core MVP (the GEO engine)

Goal: the six pipeline steps + providers, each unit-tested at $0 under
`DRY_RUN=1`, wired into the worker so a claimed job runs end-to-end and persists
partial results after every step (FR-3–FR-5, FR-8). Build test-first
([test-suite.md](test-suite.md) §8).

### P2.1 — Provider interface + mock + registry
- **Goal:** `providers/base.py` (`Provider` Protocol: `name`, `model`,
  `generate(prompt) -> ProviderResult(text, model, cost_usd)`); `providers/mock.py`
  (deterministic — mentions company iff `sha256(prompt).digest()[0] % 2 == 0`,
  cost 0); `providers/registry.py` (`get_panel` → 4 `MockProvider`s when
  `DRY_RUN`, else map `PANEL_ENGINES`; `get_analysis_provider` for the KYC call).
- **Why now:** every downstream step and test depends on the mock + registry.
- **Dependencies:** P1.1.
- **Complexity:** M
- **Deliverables:** `backend/app/providers/{base.py,mock.py,registry.py}`.
- **Acceptance:** `DRY_RUN=1` yields four mocks named after the panel engines; the
  mock is deterministic and free; registry is the single provider entry point.
- **Status:** done (session 1)

### P2.2 — Real + stub providers
- **Goal:** `anthropic_provider.py` (real, `claude-haiku-4-5-20251001`, anthropic
  SDK, `max_tokens=1024`, cost = tokens × a price-table constant);
  `openai_provider.py` (real, `gpt-5-nano` — cheapest, operator directive session 6, openai SDK); `gemini_provider.py` +
  `perplexity_provider.py` (STUBS: canned plausible answer that *sometimes
  mentions nothing*, model `"stub"`, cost 0).
- **Why now:** completes the panel shape; real adapters are exercised only via
  `respx` in tests (never a live call — [test-suite.md](test-suite.md) §1).
- **Dependencies:** P2.1.
- **Complexity:** M
- **Deliverables:** `backend/app/providers/{anthropic_provider,openai_provider,gemini_provider,perplexity_provider}.py`.
- **Acceptance:** each satisfies the `Provider` protocol; real adapters unit-test
  their HTTP shape under `respx`; stubs return `cost_usd=0`, model `"stub"`.
- **Status:** done (session 1)

### P2.3 — Discovery
- **Goal:** `pipeline/discovery.py` `discover(url) -> str`: httpx GET (15s timeout,
  UA `YankiBot/0.1`), BeautifulSoup parse, drop script/style/nav, homepage text +
  up to 5 same-domain links, cap ~20k chars; unreachable/empty →
  `PipelineError("could not read the site")`.
- **Why now:** step 1 of the loop; feeds KYC.
- **Dependencies:** P1.1.
- **Complexity:** M
- **Deliverables:** `backend/app/pipeline/discovery.py`, `pipeline/errors.py`
  (`PipelineError`).
- **Acceptance:** reachable page → non-empty text; unreachable → `PipelineError`,
  no crash (test-suite §3.2, via `respx`).
- **Status:** done (session 1)

### P2.4 — KYC
- **Goal:** `pipeline/kyc.py` `generate_kyc(text, url, provider) -> KYC`: one LLM
  call for strict JSON; strip ```json fences; validate against Pydantic `KYC`
  (company, description, industry, aliases — always include company name +
  registrable domain without TLD; products/services/keywords/locations/
  competitors default `[]`).
- **Why now:** step 2; its output drives prompt generation and footprint aliases.
- **Dependencies:** P2.1.
- **Complexity:** M
- **Deliverables:** `backend/app/pipeline/kyc.py`, the `KYC` model.
- **Acceptance:** given canned model output, parses + validates; `aliases`
  contains the company name and the domain name (test-suite §3.2).
- **Status:** done (session 1)

### P2.5 — Prompts (deterministic templates)
- **Goal:** `pipeline/prompts.py` `generate_prompts(kyc, count) ->
  list[PromptSpec]`: cycle categories (recommendation / comparison / alternatives
  / best-of / use-case), fill from KYC, no LLM. Exactly `count`, all non-empty, no
  duplicates.
- **Why now:** step 3; pure + free + the widest unit-test surface.
- **Dependencies:** P2.4 (`KYC` shape).
- **Complexity:** S
- **Deliverables:** `backend/app/pipeline/prompts.py`, `PromptSpec`.
- **Acceptance:** exactly `count` specs, each non-empty with a category, no dupes
  (test-suite §3.2). Aim ~100% branch coverage.
- **Status:** done (session 1)

### P2.6 — Execute (fan-out + llm_cache)
- **Goal:** `pipeline/execute.py`: for each prompt × each panel engine, consult
  `llm_cache` (fresh <24h) else call the provider, then insert a `responses` row
  and a cache row; enforce `MAX_RESPONSES_PER_JOB` (stop + log); persist after each
  response (crash-safe).
- **Why now:** step 4; the cost-control + audit-trail heart (FR-4, FR-8).
- **Dependencies:** P2.1, P2.5, P1.2.
- **Complexity:** L
- **Deliverables:** `backend/app/pipeline/execute.py`.
- **Acceptance:** one `responses` row per engine per prompt; a warm cache means no
  second provider call; `MAX_RESPONSES_PER_JOB` never exceeded (test-suite §3.2).
- **Status:** done (session 1)

### P2.7 — Footprint
- **Goal:** `pipeline/footprint.py` `detect(raw_text, kyc) -> (bool, snippet|None)`:
  pure, deterministic, case-insensitive search over company/aliases/domain; on hit
  return a ±60-char snippet around the first match; no LLM.
- **Why now:** step 5; the "show our work" evidence (FR-5).
- **Dependencies:** P2.4 (`KYC`).
- **Complexity:** S
- **Deliverables:** `backend/app/pipeline/footprint.py`.
- **Acceptance:** present → `(True, snippet)`; absent → `(False, None)`;
  deterministic (test-suite §3.2). Aim ~100% branch coverage.
- **Status:** done (session 1)

### P2.8 — Scoring
- **Goal:** `pipeline/scoring.py` `geo_score(footprints, total) -> float`: pure;
  `0.0` when `total==0` (ADR-11, no divide-by-zero).
- **Why now:** step 6; the number the whole product sells (must be provably
  correct).
- **Dependencies:** none.
- **Complexity:** S
- **Deliverables:** `backend/app/pipeline/scoring.py`.
- **Acceptance:** `score == footprints/total`; `total==0` → `0.0` (test-suite
  §3.2). Aim 100% coverage.
- **Status:** done (session 1)

### P2.9 — Pipeline orchestrator (wire into worker)
- **Goal:** a `run_pipeline(session, analysis_id, settings)` entry point that runs
  discovery → kyc → prompts → execute → footprint → scoring in order, updating
  `status`/`progress`/`current_step` per the SPEC mapping (15/30/45/80/90/100),
  heart-beating `claimed_at`, persisting each step's output; the P1.6 worker calls
  it.
- **Why now:** turns six modules into the running loop; the seam pipeline ↔
  backend-spine must agree on.
- **Dependencies:** P2.3–P2.8, P1.6.
- **Complexity:** M
- **Deliverables:** `backend/app/pipeline/runner.py` (`run_pipeline`); worker
  wiring (backend-spine imports it).
- **Acceptance:** a claimed job walks all six steps, advances progress correctly,
  and lands `done` at 100 under `DRY_RUN=1`; any step exception → `failed`, partial
  rows kept (FR-7).
- **Status:** done (session 1)

### P2.10 — Backend tests
- **Goal (a, backend-spine):** `tests/conftest.py` (client, db_session, pg_engine
  auto-skip, mock_provider fixtures), `tests/test_api.py` (Submit + Results rows),
  `tests/test_queue.py` (claim / stale-reaper / `attempts>3` on SQLite), and
  `tests/test_queue_postgres.py` (the Postgres-only `FOR UPDATE SKIP LOCKED`
  concurrency guard — runs only when `TEST_DATABASE_URL` points at a live
  Postgres, else skips).
  **Goal (b, pipeline):** `tests/pipeline/conftest.py` (sample_kyc, sample_html) +
  one test file per step per the acceptance→test map.
- **Why now:** TDD is how each step is built; `make test` must be green at
  session end.
- **Dependencies:** the code each test covers.
- **Complexity:** L
- **Deliverables:** `backend/tests/**` (split by ownership above).
- **Acceptance:** a test exists for every [02-mvp.md §8](02-mvp.md) acceptance row
  ([test-suite.md](test-suite.md) §9); `make test` green; DB tests auto-skip with
  no Postgres.
- **Status:** done (session 1)

---

## Phase 3 — Usable MVP (the three screens, wired end-to-end)

Goal: a human submits a URL at `:8140` and watches the six steps render into a
GEO score with every raw answer behind it — the whole-loop definition of done.

### P3.1 — API client + generated types (contract)
- **Goal:** `lib/api.ts` (thin fetch wrapper over relative `/api/v1/...`);
  `make gen-types` runs `scripts/gen_openapi.py` to export `app.openapi()` →
  `shared/contracts/openapi.json`, then `openapi-typescript` →
  `frontend/lib/types.ts` (both checked in, never hand-edited). The app never
  imports `types.ts` directly: `lib/contracts.ts` is a hand-maintained seam that
  re-exports the generated `components['schemas']` under friendly names
  (`Analysis`, `Prompt`, …) and narrows the free-form fields (`status`,
  `current_step`, `kyc`) to their locked SPEC shapes.
- **Why now:** the FE/BE contract cannot silently drift (NFR-6); the screens type
  against `contracts.ts`, which is anchored to the generated types.
- **Dependencies:** P1.5 (openapi export), P1.7.
- **Complexity:** M
- **Deliverables:** `frontend/lib/{api.ts,types.ts,contracts.ts}`,
  `scripts/gen_openapi.py`, `shared/contracts/openapi.json`.
- **Acceptance:** `make gen-types` regenerates both artifacts byte-stably; a
  contract change shows up as a diff (CI drift gate is P4.3); `contracts.ts`
  compiles against the regenerated `types.ts`.
- **Status:** done (session 1)

### P3.2 — Landing page + UrlForm
- **Goal:** `/` with headline "See how AI answers talk about your brand." and a
  `UrlForm` that validates client-side and POSTs to create an analysis, then
  routes to `/analyses/[id]`.
- **Why now:** the entry screen (FR-6).
- **Dependencies:** P3.1, brandkit components.
- **Complexity:** S
- **Deliverables:** `frontend/app/page.tsx`,
  `frontend/components/{Button,UrlForm}.tsx`.
- **Acceptance:** blank/malformed URL rejected client-side (no submit fires); a
  valid `https://…` submits and navigates.
- **Status:** done (session 1)

### P3.3 — Progress + results screen
- **Goal:** `/analyses/[id]` polls `GET` every 2s. queued/running →
  `StepProgress` (six steps from `current_step`+`progress`). done → `ScoreGauge`
  + `ResultsTable` + KYC JSON block + prompts list. failed → danger card with
  `error` + retry link.
- **Why now:** the live-progress + results screen — the payoff (FR-6, FR-7).
- **Dependencies:** P3.1, P3.2.
- **Complexity:** M
- **Deliverables:** `frontend/app/analyses/[id]/page.tsx`,
  `frontend/components/{StepProgress,ScoreGauge,ResultsTable}.tsx`.
- **Acceptance:** all three states render from the real envelope; the gauge
  exposes an aria-label describing the score.
- **Status:** done (session 1)

### P3.4 — Frontend component tests
- **Goal:** vitest + testing-library for `UrlForm` validation, `ScoreGauge`
  aria-label, and the `lib/score.ts` score→color-band helper (mock `lib/api.ts`,
  no network).
- **Why now:** the UI rows of the acceptance→test map (test-suite §9).
- **Dependencies:** P3.2, P3.3.
- **Complexity:** S
- **Deliverables:** `frontend/tests/{UrlForm,ScoreGauge}.test.tsx`,
  `frontend/tests/score.test.ts`, and `frontend/lib/score.ts` (the color-band
  helper under test).
- **Acceptance:** the three P3.4 vitest files (`UrlForm.test.tsx`,
  `ScoreGauge.test.tsx`, `score.test.ts`) are green with 9 tests; the three
  logic-bearing units have a test each. (P4.5 later grew the full
  `npm test -- --run` suite to 20 tests across 8 files.)
- **Status:** done (session 1)

### P3.5 — Playwright happy path + DRY_RUN e2e verification
- **Goal:** `e2e/happy-path.spec.ts` (submit `https://example.com` against a
  running `DRY_RUN=1` stack → six steps → assert a score renders; **gated on
  `E2E_BASE_URL`**, skipped otherwise). Then manually verify the full loop against
  `make dev`.
- **Why now:** the whole-MVP acceptance (02-mvp.md §8 last row); proves the
  session's definition of done.
- **Dependencies:** P2.9, P3.3, P1.8.
- **Complexity:** M
- **Deliverables:** `frontend/e2e/happy-path.spec.ts`,
  `frontend/playwright.config.ts`.
- **Acceptance:** with a booted DRY_RUN stack and `E2E_BASE_URL` set, the spec
  passes; unset → skipped (keeps `make test` fast + hermetic).
- **Status:** done (session 1) — spec authored and the full loop **manually**
  verified end-to-end against a live DRY_RUN stack. The automated Playwright run
  was skipped in this env (chromium needs a root `install-deps`); running it in
  CI is P4.4.

---

## Phase 4 — Polish (P4.3 + P4.4 + P4.5 + P4.6 done; P4.1 + P4.2 operator-gated)

Goal: take the working DRY_RUN loop to a live, cost-validated, CI-guarded deploy,
then start the first [roadmap.md](roadmap.md) **Next** items. Each task is sized
for one focused agent session. **Do not start any Phase-4 task until the Phase-3
happy path renders a score.**

### P4.1 — Real-key smoke test + Week-1 invoice check
- **Goal:** run one real analysis with `DRY_RUN=0` and real Anthropic + OpenAI
  keys (Gemini/Perplexity stay stubbed); confirm responses, footprints, and a
  score; capture the actual per-analysis cost and check it against the caps
  (NFR-1). Record the number for the pricing decision in
  [roadmap.md](roadmap.md) 2d.
- **Why now:** validates the cost model before anything goes public; the one thing
  DRY_RUN cannot prove.
- **Dependencies:** all of Phase 3 green.
- **Complexity:** S
- **Deliverables:** a cost note (in the session summary / feasibility doc), no
  code unless a bug surfaces.
- **Acceptance:** a real run completes within the caps; the measured cost is
  recorded; no secret is committed.
- **Status:** done (session 6, 2026-07-10) — **Anthropic leg proven live;
  OpenAI leg blocked on the operator's OpenAI billing.** The operator added
  keys and directed "cheapest models ×2": Anthropic was already on the
  cheapest (`claude-haiku-4-5-20251001`, $1/$5 per MTok); OpenAI switched
  `gpt-4o-mini` → **`gpt-5-nano`** ($0.05/$0.40 — verified vs the official
  pricing/deprecations pages; needs `max_completion_tokens` +
  `reasoning_effort="minimal"`). First live attempt failed: the OpenAI key
  returns `429 insufficient_quota` (billing, not rate-limit) — operator item.
  Re-run with a live-Anthropic panel (`PANEL_ENGINES=anthropic,gemini,
  perplexity`, stubs free) **completed end-to-end in ~40s**: real KYC profile
  for `https://www.anthropic.com` (Anthropic PBC, correct industry/keywords/
  products), `geo_score=0.2` (6/30; stubs dilute by design),
  **measured panel cost $0.0132 / analysis** (10 Haiku responses,
  ~$0.0013 each; `cost_usd` columns work). Margin check vs
  [00-first-mvp-draft.md](00-first-mvp-draft.md) NFR-1: even daily full-panel
  scans ≈ $0.45/mo/customer ≈ **1% of the $49 plan** — far under the 35%
  ceiling; no repricing needed. Residual: record the OpenAI leg (~+$0.002/
  analysis est.) once the operator fixes quota; KYC-call cost is not
  persisted to the DB (small gap, noted in tech-debt #1).

### P4.2 — Deploy to yanki.beyondkaira.com (this VPS, co-tenant with live sites)
- **Goal:** first real supervised deploy. Target retargeted by the operator
  (2026-07-10): **`yanki.beyondkaira.com`, served from the SAME VPS
  (161.97.172.146) that already hosts live sites** (pulse-prod stack, Ant
  Media, brier-db) — **the hard constraint is not disturbing them.** Exercise
  the ams-pulse-style `deploy/` scripts (build, tag by git SHA,
  `compose -p yanki-prod up`, `/healthz` check, rollback to a last-good-SHA
  file); publish through the shared pulse-prod Caddy.
- **Why now:** turns "runs on my laptop" into a shareable URL for design partners.
- **Dependencies:** P1.8, P4.1. DNS is already met: `yanki.beyondkaira.com →
  161.97.172.146` verified resolving 2026-07-10.
- **Complexity:** M
- **Topology facts (verified on the VPS 2026-07-10, drove the session-5
  post-close deploy-config changes; SUPERSEDED since — the edge moved from the
  shared Caddy to host nginx, see `deploy/MIGRATION.md`):**
  - The shared Caddy is the container `pulse-prod-caddy-1`; it mounts ONE
    config file read-only (`~/repo/ams-pulse/deploy/config/Caddyfile.prod`) —
    there is **no import dir**, so publishing Yanki means adding the site
    block from `deploy/caddy/yanki.beyondkaira.com.caddy` to that file and
    `caddy validate` + `caddy reload` (NEVER restart — other live sites
    terminate TLS on it). That edit lives in the ams-pulse repo → operator.
  - A containerized Caddy cannot reach host-loopback binds, so web + api join
    its docker network (`pulse-prod_default`, `external:`) under aliases
    `yanki-web` / `yanki-api` — the same pattern the shared Caddyfile uses for
    its own app. Consequence: the pulse-prod stack must be up before
    `make deploy`.
  - Host ports 8140 (another tenant) and 5432 (brier-db) are taken; the prod
    compose loopback binds are parameterized (`YANKI_PROD_WEB_PORT`→8142,
    `YANKI_PROD_API_PORT`→8143) and used only by deploy.sh health checks.
- **Deliverables:** `deploy/{deploy.sh,rollback.sh,...}`,
  `deploy/caddy/yanki.beyondkaira.com.caddy`, README deploy section verified.
- **Acceptance:** `make deploy` builds, migrates, health-checks, and serves
  `https://yanki.beyondkaira.com`; `make rollback` restores the last-good SHA;
  **every pre-existing site on the VPS (pulse, ams.*, etc.) still serves
  before AND after** — spot-check them around the Caddy reload and the deploy.
  (Scripts are currently marked UNTESTED tech debt — this task clears that.)
- **Status:** ✅ done (2026-07-10, session 7). All acceptance criteria met:
  `make deploy` built/migrated/health-checked (after one real fix — the web
  image needed `npm ci --include=dev`, commit 3a84943); the site serves at
  https://yanki.beyondkaira.com with valid TLS; a mock analysis ran
  end-to-end on prod; `make rollback` exercised clean; co-tenants
  (pulse/apex/www/ams) matched their pre-deploy baseline before and after
  the Caddy reload. Old tech-debt #1 repaid. Note: prod runs DRY_RUN=1
  until the operator opts into live providers.

### P4.3 — CI hardening
- **Goal:** GitHub Actions: `make lint` + `make typecheck` + `make test` (with a
  Postgres service so DB tests actually run), an **OpenAPI drift gate** (fail if
  `make gen-types` produces a diff — NFR-6), and **gitleaks** in pre-commit + CI
  (NFR-5).
- **Why now:** locks in the contract-safety and secret-safety guarantees before
  more hands touch the repo.
- **Dependencies:** P2.10, P3.1.
- **Complexity:** M
- **Deliverables:** `.github/workflows/ci.yml`, `.pre-commit-config.yaml`,
  gitleaks config.
- **Acceptance:** CI runs the full suite green on a clean PR, red on a contract
  drift or a planted secret.
- **Status:** done (session 2). The workflow now has **five** jobs: `backend`
  (ruff + mypy + pytest against a Postgres service), `frontend` (typecheck +
  lint + vitest + build), `contract` (OpenAPI drift gate), `secrets` (gitleaks
  `8.28.0`, checksum-verified binary, full-history `gitleaks git .` scan), and
  the P4.4 `e2e` job. Pre-commit adds a gitleaks hook plus basic hygiene checks
  (`check-merge-conflict`, `detect-private-key`, `check-added-large-files`) in
  `.pre-commit-config.yaml`; `gitleaks/gitleaks-action` was deliberately avoided
  (it requires a `GITLEAKS_LICENSE` for org repos). **Deliverable deviation:** no
  `.gitleaks.toml` was written — the clean full-history scan needed no allowlist;
  add one only if a future false positive demands it. Everything provable locally
  was proven, including both the RED path (planted secret flagged, direct scan
  and via the pre-commit hook) and the GREEN path (clean 5-commit history).
  **First-push proof landed 2026-07-10** (run 29058049101 on
  `aytekXR/yanki-mvp`): backend, frontend, contract-drift, and secrets all
  green on the first-ever real-runner execution — the P4.3 jobs are proven.
  (The fifth job, P4.4's e2e, went green in session 4 after its install-order
  fix; see P4.4.) Session 4 also bumped the action majors off the deprecated
  Node-20 runtime (checkout v7, setup-node v6, setup-uv v7 — v8 dropped
  floating major tags, so v7 keeps the repo's `@vN` pin style).

### P4.4 — Playwright in CI
- **Goal:** a CI job that boots the `DRY_RUN=1` stack, sets `E2E_BASE_URL`, and
  runs `e2e/happy-path.spec.ts`.
- **Why now:** guards the whole-loop against regressions once it's shared.
- **Dependencies:** P3.5, P4.3.
- **Complexity:** S
- **Deliverables:** an e2e job in `.github/workflows/`.
- **Acceptance:** the happy path runs (not skipped) and passes in CI.
- **Status:** done (session 4 — proven in CI). The `e2e` job in
  `.github/workflows/ci.yml` runs `npm ci` + `npx playwright install
  --with-deps chromium` **first**, then writes `deploy/.env` with `DRY_RUN=1`,
  brings the stack up (`docker compose up -d --build`), waits on api
  `:8141/healthz` and web `:8140`, runs `e2e/happy-path.spec.ts` with
  `E2E_BASE_URL=http://localhost:8140`, dumps compose logs on failure, and
  tears down (`down -v`, always). The first-push run (29058049101) had the
  installs *after* the boot and died `EACCES`: dockerd creates the missing
  anonymous-volume mountpoint `frontend/node_modules` on the host as root.
  The reorder was reproduced/verified locally in a scratch checkout, then
  **run 29059944092 went green: `1 passed (6.6s)` — the spec's first-ever
  execution, not skipped** (acceptance met). Known accepted dependency: the
  discovery step really fetches example.com even under DRY_RUN, so the job
  needs runner egress (tech-debt #8).

### P4.5 — Accessibility + polish audit
- **Goal:** audit the three screens against [frontend-brandkit.md](frontend-brandkit.md)
  §7 (contrast, focus states, aria, keyboard nav, reduced-motion) and fix gaps;
  tidy loading/empty/error states.
- **Why now:** the checker is a public marketing surface — accessibility is table
  stakes before launch.
- **Dependencies:** Phase 3 green.
- **Complexity:** M
- **Deliverables:** frontend fixes; a short audit note.
- **Acceptance:** the §7 checklist passes; no critical axe violations on the three
  screens.
- **Status:** done (session 2). The audit produced 9 findings (A1–A9); **8 are
  fixed, A8** (per-state `document.title`) **deferred as MVP gold-plating.**
  Fixes: new `success-700` (`#15803d`) / `danger-700` (`#b91c1c`) token shades
  for text/glyphs on the `-soft` fills (badges/headings/checks raised to
  ≥4.5:1), a stronger `UrlForm` input border (`surface-subtle #64748b`) for WCAG
  1.4.11, `role="alert"` on the failure card and `role="status"` on the loading
  paragraph, a 40px-min "Try another URL" target, and an empty-responses guard.
  New axe smoke tests cover all three screens (`tests/*.a11y.test.tsx`).
  **Caveat:** axe's `color-contrast` rule cannot run under jsdom (no
  layout/paint), so the contrast fixes are guarded by manually computed ratios,
  not automated tests.

### P4.6 — Kick off roadmap "Next" (free public checker)
- **Goal:** the first [roadmap.md](roadmap.md) **Next** slice — begin 2a (public
  no-signup checker: brand + category → fixed prompts × 4 engines, cached 24h,
  rate-limited, email-gated). Break it into P5.x tasks in a follow-up session.
- **Why now:** the checker is the demand test and launch wedge; it ships weeks
  before the app.
- **Dependencies:** all of Phase 4 above; a green, deployed MVP.
- **Complexity:** L (multi-session — decompose first)
- **Deliverables:** a new **Phase 5** task breakdown in this doc; no build until
  decomposed.
- **Acceptance:** Phase 5 tasks exist, each session-sized; scope stays frozen per
  02-mvp.md §4 until the MVP is signed off.
- **Status:** done (session 3) — planning only, per the acceptance: the **Phase 5**
  section below (preamble + build gate + lanes/merge risks + P5.1–P5.11) is the
  deliverable. Produced by a 3-proposal (lean-ship / abuse-cost-first /
  wedge-first) → 3-judge → synthesis → 3-lens adversarial-verify orchestration,
  with the final verifier findings hand-adjudicated (notably: leads/demand made
  per-submit via `checker_submissions` so the 24h cache can't lose leads). No
  build started. **Dependency deviation (recorded):** the *decomposition* ran
  before P4.1/P4.2 per the session-2 brief's neither-gate-unblocked branch — the
  listed dependencies gate the Phase-5 *build*, which stays frozen. See
  [sessions/2026-07-10-01.md](sessions/2026-07-10-01.md).

---

## Phase 5 — Free public checker (roadmap 2a)

**Phase goal.** Ship the free, no-signup public checker: a visitor types a
**brand + category**, we run **12 fixed prompts × 4 engines** live, and they see a
GEO score, an engine-by-engine presence map, the **competitors that showed up**,
and at least one full raw answer — the full report costs an email address. English
**and** Turkish. This is the demand test, the lead magnet, and the launch asset in
one ([roadmap.md](roadmap.md) 2a; [00-first-mvp-draft.md](00-first-mvp-draft.md)
"The free checker").

> **⚠ Scope change, 2026-07-10 (operator directive, post-session-12): the
> whole product is ENGLISH-ONLY.** P5.8 + P5.9 (and their ADR-24/ADR-25) are
> **skipped**, the Turkish coupling notes in the preamble below are void, and
> P5.10/P5.11 lose their Turkish gates (their cards carry the amendment).
> Turkish moved to the roadmap's **Later** bucket, to be revived only on the
> operator's word. In the same directive: **P5.12 (brandkit v2 UI refactor)
> was added and jumps the queue ahead of P5.4** — the checker frontend gets
> built once, on the new tokens, not built then re-skinned. Gemini/Perplexity
> key FIELDS are staged in `deploy/.env` + `.env.example` (inert until P5.7);
> the operator pastes real keys at their convenience.

**Design stance (why this is small).** The checker is a *thin variation of the loop
we already run*, not a new product. It reuses the existing six-step pipeline, the
`analyses`/`prompts`/`responses`/`llm_cache` tables, the Postgres-as-queue worker,
the provider registry, the `GET /api/v1/analyses/{id}` envelope, and the
`ScoreGauge`/`ResultsTable`/`StepProgress` components **unchanged**. Only four
things vary: (1) the input is brand+category, so step 1 "discovery" builds a seed
string instead of crawling a URL and step 2 KYC runs **as-is** (aliases fall out
for free, and the reused KYC keeps the DRY_RUN score coherent — see below); (2)
step 3 uses a **fixed, version-stamped** bilingual 12-prompt set instead of
`PROMPT_COUNT` generated prompts; (3) two read-time results (presence map +
competitors) are computed from rows we already store; (4) a public surface needs
abuse guards and a lead capture. Net new persistence: nullable columns on
`analyses` (`kind`, `brand`, `category`, `lang`) plus **one small append-only
table**, `checker_submissions` — one row per checker submit (cache-served hits
included) carrying `ip_hash`, `lang`, and a nullable lead `email`. The table
exists because the 24h per-brand cache shares one `analyses` row across many
visitors: leads and demand counting must be per-**submit**, or repeat visitors to
a hot cached brand would overwrite each other's emails and cache hits would
vanish from the demand numbers. Net new endpoints: **two**
(`POST /api/v1/checker`, `POST /api/v1/checker/leads`), both extending the OpenAPI
app through the `make gen-types` flow. No Redis, no queue, no new infrastructure —
the boring stack stays boring (NFR-4, ADR-2).

**Build-start GATE.** Phase 5 stays **frozen** until the MVP is signed off — the
[02-mvp.md §3](02-mvp.md) in-scope flow, which that doc calls "the sole definition
of done" — with the Phase-4 gate above: **P4.1** (real-key smoke + Week-1
invoice check) **and** **P4.2** (deploy to `yanki.beyondkaira.com`) **and** the
**first green CI run** (the
first push to a GitHub remote, which is what first exercises all five CI jobs and
the Playwright e2e). No P5 task starts before those three land. This preamble and
the task list are the *decomposition* deliverable of **P4.6** — planning only.

**How this handles the 2b/2c coupling.** The roadmap says the checker "needs both
[engine depth 2b and Turkish 2c] to be credible." We take the **minimal slice of
each and ruthlessly defer the rest** — we do **not** absorb 2b/2c/2d:

- **2b (engine depth) — minimal slice INCLUDED:** make **Gemini (with search
  grounding) + Perplexity real** (P5.7). A public "show your work" page cannot
  display canned *stub* answers under a "Gemini"/"Perplexity" label — that would
  break the one wedge the checker exists to prove. Per ADR-9 each is a single-file
  swap behind the existing `Provider` protocol, so this is genuinely small.
  **DEFERRED (ships degraded, honestly):** the weighted 0–100 score,
  2-samples-per-prompt, and the sentiment/position extraction pass. The checker
  ships with the **binary** score `footprints / total_responses` — which the
  roadmap itself calls "the honest placeholder until [the weighted score] lands."
  The methodology page (P5.10) says so out loud. These belong to the paid tracking
  pipeline (2b/2d), not the free checker.
- **2c (Turkish) — minimal slice INCLUDED:** a **native** (not translated)
  bilingual fixed prompt set + **Turkish suffix-aware footprint matching with the
  dotted/dotless-i (İ/ı) casefold guard** + Turkish UI copy (P5.8, P5.9). Because
  the checker uses a *fixed* 12-prompt set, "native Turkish prompt generation"
  collapses from an engine into a **curated bilingual list** — a fraction of 2c's
  scope. **DEFERRED:** the full native prompt-*generation* engine and the
  cheap-model extraction validated on a labelled corpus — those exist for the app's
  30–60 site-derived prompts and the weighted score (2c/2d), neither of which the
  binary checker uses. **Hard launch rule:** if a native speaker cannot sign off
  the 12 TR prompts and the casefold fixtures, the checker **launches EN-only** (no
  Turkish beats bad Turkish) — a P5.11 go/no-go condition.
- **Sequencing of the coupling:** the English vertical (P5.1–P5.5) is built and
  proven end-to-end under `DRY_RUN=1` first, so a working checker can go to the 5
  design-partner agencies as a soft preview early. The **loud public launch is
  gated** on real engines (P5.7), Turkish (P5.8/P5.9), the abuse guards (P5.6), and
  the "show our work" methodology page (P5.10) all being done — enforced by P5.11.

**Why KYC is reused as-is (not a synthesized "KYC-lite").** The checker keeps the
existing KYC step rather than skipping it for a brand-derived stub, for two
reasons. (1) It is **zero new code** — the smallest possible diff, the phase's
whole stance. (2) It keeps the **DRY_RUN demo coherent**: the mock KYC returns the
`Yanki Demo Co` profile (aliases include "Yanki") and the mock execution answers
mention "Yanki Demo Co" ~half the time, so footprint matching yields a **meaningful
~0.5 score** — exactly what a design-partner soft preview needs. A KYC-lite whose
aliases are the *real* submitted brand would find nothing in the mock answers
(which still name "Yanki Demo Co") and collapse the DRY_RUN score to ~0. Under
**real** keys the real KYC call returns the real brand's profile, so the displayed
brand is correct at launch; only the $0 DRY_RUN run shows "Yanki Demo Co"
(tech-debt #3, expected). The one extra analysis-model call per uncached check is
negligible against the 48 execution probes it accompanies.

**Everything is $0-first.** Every task is buildable and testable under `DRY_RUN=1`
on the deterministic `MockProvider` (a checker run comes back about "Yanki Demo
Co", tech-debt #3 — fine and expected). Real-key and live steps are isolated into
the one operator-gated task (P5.11), mirroring P4.1/P4.2. Real Gemini/Perplexity
adapters (P5.7) are exercised only via `respx`, never a live call in CI (the P2.2
pattern).

**New ADRs this phase** (design.md ADR log continues from ADR-18; each recorded
when its task lands — numbered by *planned* build order; the independent P5.6/P5.7
may land early, so land order can differ from the numbering): **ADR-19** checker as
a `kind` of analysis (reuse `analyses`) plus the append-only `checker_submissions`
table for per-submit demand + lead capture — P5.1; **ADR-20** `llm_cache` upsert for concurrent-worker safety (repays
tech-debt #6) — P5.2; **ADR-21** competitors computed from the raw answers via a
deterministic proper-noun co-mention heuristic (not `kyc.competitors`, not an LLM
pass) — P5.3; **ADR-22** Postgres-derived rate limiting + daily cost cap +
`CHECKER_ENABLED` kill-switch + salted `ip_hash`, no Redis — P5.6; **ADR-23** real
Gemini/Perplexity providers (supersedes ADR-9 for the checker panel) — P5.7;
**ADR-24** Turkish suffix-aware + İ/ı-casefold footprint matching and the fixed
native TR prompt set — P5.8; **ADR-25** a plain typed i18n dictionary (no
`next-intl`) — P5.9.

### Sequencing & lanes (parallelism map)

Build order is **P5.0 first** (added session 8 — see its card), then
P5.1 → P5.11. After **P5.1** lands the schema + submit endpoint, the
pipeline and frontend lanes run in parallel against the contract; **P5.6**
(hardening) and **P5.7** (real engines) are independent and can run any time;
**P5.8/P5.9** (Turkish) layer onto the green English vertical; **P5.10**
(methodology) renders the version-stamped **EN+TR** prompt module (P5.2/P5.8) and
layers its copy onto the filled TR i18n dict, so it follows **P5.8/P5.9**. **P5.11**
is the strictly-last operator go-live.

| Task | Lane | Depends on | Can parallel with |
|---|---|---|---|
| P5.0 minimal rate limit on the LIVE analyses endpoint | backend-spine | none (urgent) | all |
| P5.1 checker submit + leads + 24h reuse | backend-spine | P4.1/P4.2/CI (gate) | — (unblocks the rest) |
| P5.2 checker pipeline branch + fixed EN prompts + cache upsert | pipeline | P5.1 | P5.6, P5.7 |
| P5.3 presence map + competitors (read-time) | backend-spine | P5.1, P5.2 | P5.6, P5.7 |
| P5.4 checker frontend (EN): landing + results | frontend | P5.1, P5.3 | P5.6, P5.7 |
| P5.5 email gate + full-report reveal | frontend | P5.1, P5.4 | P5.6, P5.7 |
| P5.6 hardening: kill-switch + rate limit + cost cap | backend-spine | P5.1 | P5.2, P5.3, P5.4, P5.5, P5.7 |
| P5.7 real Gemini + Perplexity | pipeline | none (gate only) | all |
| ~~P5.8 Turkish prompts + TR footprint matching~~ | — | **SKIPPED 2026-07-10 (EN-only directive)** | — |
| ~~P5.9 Turkish UI + i18n~~ | — | **SKIPPED 2026-07-10 (EN-only directive)** | — |
| P5.10 methodology page ("show our work") — EN-only | frontend + infra | P5.2, P5.4 | P5.6, P5.7 |
| P5.11 operator: live 4-engine smoke + deploy | infra (operator-gated) | all non-skipped above | — |
| P5.12 brandkit v2 UI refactor (added 2026-07-10; runs BEFORE P5.4) | frontend | none | P5.6, P5.7 (backend lanes) |

**Shared-contract merge risks (coordinate before editing):**
- **OpenAPI envelope.** P5.1 (new endpoints/request schemas) and P5.3 (`ResultOut`
  gains nullable `engine_presence` + `competitors_appeared`) both regenerate
  `shared/contracts/openapi.json` → `frontend/lib/types.ts` via `make gen-types`
  (never hand-edited; +lead review). Land P5.1 then P5.3 **before** the frontend
  (P5.4) locks its `contracts.ts` narrowings, or accept one regen.
- **`backend/app/api/routes.py`** is hand-edited by **P5.1** (the two new routes),
  **P5.3** (`_to_out` fills the new result fields), and **P5.6** (submit-handler
  enforcement + IP hashing + kill-switch) — all backend-spine. P5.3 (`_to_out`) and
  P5.6 (the submit handler) touch **different functions**, so parallel edits rarely
  textually collide; still, coordinate/sequence the two if run in parallel (same
  lane, one owner) to keep this shared file merge-clean.
- **The `analyses` model + the one new Alembic migration** is owned by
  **backend-spine** (P5.1). It adds *only nullable* columns (+extra-sensitive
  `alembic/**` review). `ip_hash` lands in P5.1's migration so P5.6 is pure logic
  with **no** second migration; the pipeline lane reads `analysis.kind` but must
  not alter the migration.
- **`runner.py` kind-branch stays in the pipeline lane (P5.2).** The worker
  (`app/worker.py`, backend-spine) calls `run_pipeline` **unchanged** — the
  `kind`-branch lives inside `run_pipeline`, so there is **no** worker-dispatch seam
  and no separate `checker_runner` (deliberately more minimal than a parallel
  runner). P5.2 only reads P5.1's `kind` column; sequence P5.1 → P5.2. **P5.8**
  later edits the same file only to thread `analysis.lang` into the footprint step
  (same pipeline lane; sequence P5.2 → P5.8).
- **`checker_prompts.py`** (fixed set, `VERSION`-stamped) is edited by P5.2 (EN)
  then P5.8 (TR) — same lane (pipeline), sequence them. P5.10 renders from a
  generated JSON export of this same module (via `make gen-types`), never a
  hand-copy.
- **`footprint.py`** is edited only by P5.8 (TR suffix + İ/ı casefold). P5.3's
  summary helper does **not** import it (presence uses the already-stored
  `footprint` booleans; competitors use their own proper-noun scan), so P5.3 and
  P5.8 do not collide.
- **Config env vars** bind all lanes; the new vars (below) are added to
  `app/config.py` **and** `deploy/.env.example` in the task that introduces them.
- **`deploy/.env.example` is infra-owned and extra-sensitive (lead review).**
  P5.1, P5.6, and P5.7 each append vars to it — every such edit gets the infra
  lane's review. Likewise `app/config.py` is backend-spine-owned: P5.7 (pipeline
  lane) adding its two keys coordinates with the spine owner.
- **`Makefile` + `scripts/**` are infra-owned.** P5.10's generator
  (`scripts/gen_methodology.py`) and its `make gen-types`/CI wiring are the
  **infra half** of that task; the frontend half only renders the generated
  artifact. Run P5.10 as one agent granted both ownerships or split the halves —
  and the same task reconciles design.md §2's "two files are produced by
  `make gen-types`" statement to name the third generated artifact.
- **`CHECKER_ENABLED` defaults to `0`** (P5.6). `deploy/.env.example` ships it `0`
  (prod stays dark); local dev and the CI e2e job set `CHECKER_ENABLED=1`; the
  operator flips prod to `1` at go-live (P5.11).
- **`lib/i18n.ts`** is scaffolded (EN) by P5.4, filled (TR) by P5.9, then extended
  with the methodology copy keys by P5.10 — all frontend-lane, sequence
  **P5.4 → P5.9 → P5.10** (P5.10 also **writes** it, so it is not merely a reader).

**New env vars introduced this phase** (all with safe defaults; declared in
`app/config.py` and `deploy/.env.example` — one var, one place — when their task
lands):
`CHECKER_RESULT_CACHE_HOURS=24` (P5.1); `CHECKER_ENABLED=0`,
`CHECKER_RATE_LIMIT_PER_IP_HOUR=5`, `CHECKER_RATE_LIMIT_PER_BRAND_DAY=3`,
`CHECKER_DAILY_USD_CAP=50`, `RATE_LIMIT_SALT` (P5.6); `GEMINI_API_KEY` +
`PERPLEXITY_API_KEY` (P5.7, blank under `DRY_RUN`). The fixed prompt set is a
constant **12** (not a knob); 12 × 4 engines = 48 responses ≤ the existing
`MAX_RESPONSES_PER_JOB=60`, so no cap change is needed.

---

### P5.0 — Minimal per-IP rate limit on the LIVE `POST /api/v1/analyses` (added session 8)
- **Goal:** stop unmetered spend on the endpoint that is ALREADY public with
  real keys. Session 8 flipped prod to DRY_RUN=0 (operator directive), which
  activated tech-debt #2's risk *now* — and P5.6-as-written only rate-limits
  the future `/api/v1/checker` endpoint, not this one. Minimal slice: count
  `analyses` rows created in the last hour (per hashed client IP, stored in a
  new nullable `analyses.ip_hash` column, salted like P5.1's design) and
  reject over `ANALYSES_RATE_LIMIT_PER_IP_HOUR` (default 5) with a 429 +
  `Retry-After`; plus a global `ANALYSES_DAILY_CAP` (default 100/day across
  all IPs) as the blunt cost backstop. No new infra — one migration, one
  check in the POST route, config, tests.
- **Why now:** the plan's original assumption was "rate limiting lands before
  any public URL with real keys" (tech-debt #2). The operator chose to go
  live first — this task restores the safety property with the smallest diff.
- **Dependencies:** none (deliberately independent of the checker schema;
  P5.1 may reuse the `ip_hash` column/salt helper).
- **Complexity:** S
- **Deliverables:** Alembic migration (nullable `analyses.ip_hash`),
  `services/rate_limit.py` (reused later by P5.6), route check, config vars in
  `deploy/.env.example` + architecture.md, backend tests (429 over-limit,
  header, cap), OpenAPI regen if the error envelope changes.
- **Acceptance:** 6th submit from one IP within an hour on prod returns 429
  (verify live, then reset); existing e2e/CI stay green; a redeploy applies
  the migration cleanly.
- **Status:** ✅ done (session 9, commit 31061c0; deployed, 429 verified live
  with Retry-After 3587, then reset). Bonus: limit `0` acts as a kill-switch
  (429 everything) instead of crashing.

### P5.1 — Checker submit endpoint + lead capture + per-brand 24h reuse
- **Goal:** the checker's API surface, reusing the `analyses` table. One Alembic
  migration (a) adds **nullable** columns to `analyses` (`kind` default `'mvp'`,
  `brand`, `category`, `lang` default `'en'`) and (b) creates the append-only
  **`checker_submissions`** table (`id`, `analysis_id` FK, `ip_hash` nullable,
  `lang`, `email` nullable, `created_at`) — one row per accepted checker submit,
  because the 24h cache shares one `analyses` row across visitors and leads/demand
  must be counted per submit. New `POST /api/v1/checker {brand, category, lang}` →
  validates; every accepted submit **inserts a `checker_submissions` row** (the
  demand signal, cache hits included); if a `done`
  checker analysis with the same normalized `(brand, category, lang)` exists and is
  younger than `CHECKER_RESULT_CACHE_HOURS` (24) it **returns that analysis id**
  (instant, $0 — the draft's "results cached 24h per brand" abuse mitigation);
  otherwise it inserts a `kind='checker'` row `status='queued'`. Either way it
  returns **202 `{id, submission_id}`**.
  Because `analyses.url` is an existing MVP column with a `NOT NULL` constraint we
  deliberately do **not** alter (the migration stays *nullable-columns-only*), a
  checker row — which has no crawl target — stores a **deterministic synthetic**
  `url` (`f"checker://{normalized_brand}/{category}"`) in `create_checker_analysis`,
  so the insert satisfies the constraint with **no** schema/constraint change and no
  MVP-column mutation under the `alembic/**` review. New
  `POST /api/v1/checker/leads {submission_id, email}` sets `email` on **that
  submission row** (the email gate) — append-only, so two visitors served the same
  cached analysis each keep their own lead; a shared row never loses an email to an
  overwrite. `ip_hash` stays null here (populated in P5.6,
  which owns the salt); the column lands now so P5.6 needs no second migration.
  Results are polled through the **existing** `GET /api/v1/analyses/{id}` (works for
  checker rows unchanged).
- **Why now:** it is the foundation every other P5 task builds on and the contract
  the pipeline + frontend lanes code against in parallel.
- **Dependencies:** the P5 build gate (P4.1 + P4.2 + first green CI).
- **Complexity:** M
- **Deliverables:** `backend/alembic/versions/<rev>_checker_fields.py` (migration
  #2: nullable `analyses` columns + the `checker_submissions` table),
  `backend/app/db/models.py`, `backend/app/api/schemas.py`
  (`CheckerSubmitRequest`, `CheckerSubmitResponse`, `CheckerLeadRequest`),
  `backend/app/api/routes.py` (two routes), `backend/app/services/analyses.py`
  (`create_checker_analysis` with 24h reuse + per-submit recording, `attach_lead`),
  `backend/app/config.py`
  (`checker_result_cache_hours`), `deploy/.env.example`
  (`CHECKER_RESULT_CACHE_HOURS=24`; infra-owned — lead review), regenerated
  `shared/contracts/openapi.json`
  + `frontend/lib/types.ts` (via `make gen-types`), ADR-19 recorded in
  [design.md](design.md), `backend/tests/test_checker_api.py`.
- **Acceptance:** `POST /api/v1/checker` with a non-empty brand+category → `202`
  `{id, submission_id}` and the row has `kind='checker'` with a non-null synthetic
  `url` (the
  existing `NOT NULL` constraint satisfied, migration still additive-only);
  a blank brand → `422` and records nothing; a repeat submit
  within 24h returns the **same** analysis id with **no** new `analyses` row but a
  **new** `checker_submissions` row (assert analyses count unchanged, submissions
  count +1 — cache hits still count as demand); two **different** emails submitted
  via `POST /api/v1/checker/leads` against two submissions of the **same** cached
  analysis both persist and are both retrievable (no overwrite); existing MVP
  `POST /api/v1/analyses` behaviour is unchanged (defaults preserve `kind='mvp'`);
  `make gen-types` produces no drift after commit; `make test` green (DRY_RUN, $0).
- **Status:** ✅ done (session 9, commit a8f0a06; deployed, migration 0003 +
  backfill verified on prod, cache-hit + lead smoke passed at $0). Extra
  (verifier-caught): `jobs/queue.py::claim_next` now skips `kind='checker'`
  rows so the MVP worker can't fail them crawling `checker://` — **P5.2 must
  remove this guard** when the runner branches on `kind`.

### P5.2 — Checker pipeline branch: seed KYC + versioned fixed 12-prompt set (EN)
- **Goal:** teach the runner to walk the *same six steps* for a checker row without
  a crawl. In `run_pipeline`, branch on `analysis.kind`: for `'checker'`, step 1
  ("discovery") builds a seed string (`f"Brand: {brand}. Category: {category}."`)
  instead of `discovery.discover(url)` — keeping `current_step='discovery'`,
  `progress=15`, so the locked progress mapping and `StepProgress` contract are
  untouched — then KYC (step 2) runs **as-is** on the seed. Step 3 uses a **fixed,
  `VERSION`-stamped** bilingual 12-prompt set (`checker_prompts.generate(kyc, lang)`,
  English wired here; Turkish added in P5.8) instead of the templated `PROMPT_COUNT`
  generator. Steps 4–6 (execute, footprint, scoring) run unchanged. Also make
  `execute._write_cache` an **upsert** (`INSERT … ON CONFLICT (cache_key) DO
  NOTHING`, then re-read) so the public checker is safe with more than one worker
  (repays tech-debt #6; SQLite supports `ON CONFLICT DO NOTHING`).
- **Why now:** it turns the existing loop into the checker loop with the smallest
  possible diff; the whole English vertical is DRY_RUN-green once this lands.
- **Dependencies:** P5.1 (`kind`/`brand`/`category`/`lang` columns).
- **Complexity:** M
- **Deliverables:** `backend/app/pipeline/checker_prompts.py` (fixed EN set of 12,
  keyed by `lang`, carrying a module `VERSION` constant),
  `backend/app/pipeline/runner.py` (kind branch),
  `backend/app/pipeline/execute.py` (upsert),
  `backend/tests/pipeline/test_checker_prompts.py`,
  `backend/tests/pipeline/test_checker_pipeline.py`,
  `backend/tests/pipeline/test_execute_race.py` (Postgres-only concurrent-write
  test, gated like `test_queue_postgres.py`); tech-debt.md #7 marked repaid;
  ADR-20 recorded in [design.md](design.md).
- **Acceptance:** a `kind='checker'` analysis under `DRY_RUN=1` walks all six steps
  with **no** HTTP crawl, produces exactly **12** prompts and **48** responses
  (12 × 4 mock engines) ≤ `MAX_RESPONSES_PER_JOB`, lands `done` at `progress=100`
  with a meaningful non-zero `geo_score` and no divide-by-zero; `generate(kyc,'en')`
  returns 12 non-empty, category-tagged, unique prompts and is byte-stable across
  runs (version-stamped); a stale-claim re-run is idempotent (no doubled rows); two
  workers inserting the same `cache_key` at once both succeed with no `IntegrityError`.
  `make test` green. **Also (added session 9): remove the `claim_next`
  `kind='checker'` skip-guard in `backend/app/jobs/queue.py` in the same
  change that lands the runner branch, and keep its
  `test_claim_next_skips_checker_rows` replaced by a claims-checker-rows
  assertion — otherwise checker rows never run.**
- **Status:** ✅ done (session 12, commit `d6e7253` — ship, 0 blocking findings;
  guard removed, upsert PG-race-tested; prompt set `checker-en-v1` never names
  the brand: the checker measures unprompted visibility. Card's "#7 repaid" was
  a stale renumbering — the real items were #6 + #19, both repaid.)

### P5.3 — Engine-presence map + competitors-that-showed-up (read-time aggregation)
- **Goal:** surface the two checker-only results the draft promises, computed at
  read time from rows we already store — no new column, no pipeline change. A pure
  helper `services/checker_summary.py` takes the analysis' `responses` + `kyc` and
  returns `engine_presence` (per engine: mentioned count / total, derived from the
  existing `footprint` booleans) and `competitors_appeared` — a deterministic
  **proper-noun co-mention heuristic over the raw answers**: scan each answer for
  Title-Case brand tokens, **exclude** the searched brand + `kyc.aliases` + a small
  EN/TR stoplist, count frequency across answers, return the top names with their
  mention counts. This captures "brands that showed up" faithfully and at **$0** —
  it does **not** intersect against `kyc.competitors` (which would miss brands the
  KYC list never knew) and it makes no LLM call. `ResultOut` gains nullable
  `engine_presence` + `competitors_appeared`; `_to_out` populates them only for
  `kind='checker'` rows (null for MVP analyses).
- **Why now:** these are core free-tier deliverables of 2a ("engine-by-engine
  presence map + competitors that showed up") and they compose from data the
  pipeline already writes, so no worker change is needed.
- **Dependencies:** P5.1 (contract), P5.2 (checker rows to aggregate).
- **Complexity:** M
- **Deliverables:** `backend/app/services/checker_summary.py`,
  `backend/app/api/schemas.py` (`ResultOut` additions + `EnginePresence`,
  `CompetitorMention` models), `backend/app/api/routes.py` (`_to_out` fills them for
  checker rows), regenerated `shared/contracts/openapi.json` +
  `frontend/lib/types.ts`, ADR-21 recorded in [design.md](design.md),
  `backend/tests/test_checker_summary.py`.
- **Acceptance:** for a DRY_RUN checker analysis, `GET` returns `engine_presence`
  with one entry per panel engine whose counts sum-consistently with
  `total_responses`, and `competitors_appeared` listing the mock filler brands the
  answers name (**Acme, Globex, Initech, Umbrella, Stark**) — with the searched
  brand and its aliases excluded — derived from the answers alone, **not** from
  `kyc.competitors`; for an MVP (`kind='mvp'`) analysis both fields are `null`; the
  helper is pure and unit-tested; no `gen-types` drift.
- **Status:** ✅ done (session 12, commit `c5e4f6d` — ship after one fix round:
  possessive brand forms escaped exclusion, caught by the adversarial heuristic
  lens and fixed pre-merge; 23-test suite; contract additive, drift-free.)

### P5.4 — Checker frontend: bilingual-ready landing + live results (EN)
- **Goal:** the public checker screens, reusing the existing components. A new
  `/checker` route with a `CheckerForm` (brand + category inputs + an EN/TR language
  toggle; English strings wired, Turkish filled in P5.9) that calls a new
  `createCheckerAnalysis()` and routes to `/checker/[id]` (carrying the response's
  `submission_id` as a query param — P5.5's email gate posts against it). That
  results route polls
  the **existing** `getAnalysis(id)` and renders: the reused `StepProgress` while
  running (checker step copy may be relabeled — the `current_step` values are
  unchanged), then the reused `ScoreGauge`, a new `EnginePresenceMap`, a new
  `CompetitorsList`, and the raw answers (all answers shown here; the email gate that
  hides all-but-one lands in P5.5). A lightweight `lib/i18n.ts` dictionary (English
  now; a plain typed dict, not `next-intl`) backs the copy. All new components use
  [frontend-brandkit.md](frontend-brandkit.md) §2 tokens and honour §7 (never
  color-only, `aria-live` on the polling status, ≥40px targets, reduced-motion).
- **Why now:** stands up the English vertical so the whole checker runs end-to-end
  under a DRY_RUN stack and can preview to design partners before the loud launch.
- **Dependencies:** P5.1 (endpoints), P5.3 (result fields in the contract).
- **Complexity:** M
- **Deliverables:** `frontend/app/checker/page.tsx`,
  `frontend/app/checker/[id]/page.tsx`,
  `frontend/components/{CheckerForm,EnginePresenceMap,CompetitorsList}.tsx`,
  `frontend/lib/i18n.ts` (EN dict + empty `tr` placeholder), `frontend/lib/api.ts`
  (`createCheckerAnalysis`), `frontend/lib/contracts.ts` (friendly types +
  narrowings for the new fields), `frontend/tests/CheckerForm.test.tsx`,
  `frontend/tests/checker.a11y.test.tsx`.
- **Acceptance:** against a running `DRY_RUN=1` stack, submitting a brand+category
  navigates to a live progress screen that resolves into a score + presence map +
  competitors + the raw answers; blank/invalid brand is rejected client-side (no
  submit fires); the checker screens pass the axe smoke suite (no critical
  violations) per [frontend-brandkit.md](frontend-brandkit.md) §7;
  `npm test -- --run` green.
- **Status:** ✅ **done — session 13 (2026-07-10, commit `a4dbdab`)**, EN-only
  on the v2 tokens per the amended scope (no i18n machinery; `lang` not
  sent). Live-proven on the DRY_RUN stack: submit → progress → score +
  `EnginePresenceMap` + `CompetitorsList` + answers; axe suites on both
  routes. *(Amendment history: (a) EN-only — P5.9 skipped; (b) build on
  brandkit v2 — dependencies became P5.1, P5.3, P5.12. Dev note: set
  `CHECKER_ENABLED=1` in the dev env to exercise submits locally.)*

### P5.5 — Email gate + full-report reveal
- **Goal:** the checker's lead-capture conversion — the free view shows the score +
  presence map + competitors + **one** full raw answer; the rest of the answers sit
  behind an `EmailGate`. On email submit it POSTs `{submission_id, email}` to
  `/api/v1/checker/leads`
  (P5.1) — the `submission_id` from the submit response is carried to the results
  route (query param) — stores the email on that submission, and reveals all
  answers in place. The one free answer
  defaults to the first answer that mentions the brand (falls back to the first
  answer). Clear consent copy; success/error/loading states; a keyboard-accessible,
  labelled input with an inline `danger` message on an invalid email (never an alert
  box); locale-aware so P5.9 can fill TR.
- **Why now:** "the full report costs an email address" is the entire lead-magnet
  mechanic (roadmap 2a; the first-90-days target of 600 signups from 3000 runs);
  splitting it from P5.4 keeps both tasks genuinely one-session-sized.
- **Dependencies:** P5.1 (leads endpoint), P5.4 (results screen to gate).
- **Complexity:** S
- **Deliverables:** `frontend/components/EmailGate.tsx`,
  `frontend/app/checker/[id]/page.tsx` (gate wiring + one-free-answer selection),
  `frontend/lib/api.ts` (`submitLead`), `frontend/tests/EmailGate.test.tsx`,
  `frontend/tests/EmailGate.a11y.test.tsx`.
- **Acceptance:** against a `DRY_RUN=1` stack, before submit the full answer set is
  hidden behind the gate and exactly one full answer is shown; a valid email reveals
  the rest and stores it (that submission row's `email` is set — a second visitor's
  email on the same cached analysis persists alongside, never overwrites); an
  invalid email shows an
  inline error and reveals nothing; the gate is keyboard-operable with a visible
  focus ring and a ≥40px target; axe smoke passes; `npm test -- --run` green.
- **Status:** ✅ **done — session 13 (2026-07-10, commit `a4dbdab`,** same
  workflow as P5.4, one fix round). Free view = score + presence map +
  competitors + exactly one answer (first brand mention, index-0 fallback);
  valid email reveals in place; second visitor's lead persists alongside
  (proven live on the DRY_RUN stack via two distinct submissions).

### P5.6 — Public hardening: kill-switch + per-IP & per-brand rate limit + daily cost cap
- **Goal:** make the anonymous endpoint safe to expose — the blocker called out in
  tech-debt #2, required "before any public URL." All Postgres-backed, no new infra.
  (a) A `CHECKER_ENABLED` master **kill-switch** (default `0`): while off,
  `POST /api/v1/checker` returns a friendly parked **503** and enqueues nothing
  (cached-brand hits from P5.1 still return, since they cost nothing) — the public
  surface stays dark in every environment until the operator flips it at P5.11.
  (b) A `services/rate_limit.py` counts this request's **`ip_hash`** rows in
  `checker_submissions` over the last hour and rejects over
  `CHECKER_RATE_LIMIT_PER_IP_HOUR`
  with a **429**, and counts *fresh runs* (new `kind='checker'` rows) of this
  normalized `(brand, category,
  lang)` in the last day and rejects over `CHECKER_RATE_LIMIT_PER_BRAND_DAY` with a
  **429** (a single hot brand hammered from many IPs). (c) It sums today's checker
  `responses.cost_usd` and, over `CHECKER_DAILY_USD_CAP`, refuses new *runs* with a
  friendly "the free checker is at capacity today" **503** (the draft's "daily cost
  check"). `POST /api/v1/checker` derives `ip_hash = sha256(RATE_LIMIT_SALT +
  X-Forwarded-For client IP)` into `checker_submissions.ip_hash`
  (privacy-preserving behind
  the nginx edge) and enforces all guards before enqueuing.
- **Why now:** hard prerequisite for a public URL with real keys; a public,
  anonymous, LLM-spending endpoint without these is an open cost/abuse hole.
- **Dependencies:** P5.1 (`ip_hash` column; the submit route).
- **Complexity:** M
- **Deliverables:** `backend/app/services/rate_limit.py`,
  `backend/app/api/routes.py` (enforcement + IP hashing + kill-switch guard),
  `backend/app/config.py` (`checker_enabled`, `checker_rate_limit_per_ip_hour`,
  `checker_rate_limit_per_brand_day`, `checker_daily_usd_cap`, `rate_limit_salt`),
  `deploy/.env.example` (all five vars; `CHECKER_ENABLED=0`), ADR-22 recorded in
  [design.md](design.md); tech-debt.md #3 marked repaid;
  `backend/tests/test_checker_ratelimit.py`.
- **Acceptance:** with `CHECKER_ENABLED=0` a fresh submit → `503` parked and
  nothing recorded, while a 24h cached-brand submit still returns its id; with it
  `=1`, the
  `(limit+1)`-th submit from one `ip_hash` within the hour → `429`, and the
  `(limit+1)`-th distinct submit of one brand within the day → `429` (a
  cache-served repeat does **not** count); once summed checker cost exceeds a
  (monkeypatched-low) daily cap, a fresh brand+category submit → `503` while a 24h
  cached-brand submit still `202`s the existing id; `ip_hash` is a salted hash, never
  the raw IP; under `DRY_RUN` all costs are `0` so the cap never trips by default;
  `make test` green.
- **Status:** ✅ done (session 12, commit `7542751` — ship after one fix round;
  abuse-bypass lens probed XFF/counter/ordering holes. Defaults: 10/IP/h,
  20/brand/day, $5/day. Reused the P5.0 `IP_HASH_SALT` — the card's fifth var
  `rate_limit_salt` was aspirational, no second salt shipped. Card's "#3
  repaid" was stale renumbering; the real item was #21, repaid. Live-verified
  parked: prod fresh submit → 503, zero rows recorded.)

### P5.7 — Make Gemini + Perplexity real (the minimal 2b slice)
- **Goal:** replace the two **stub** providers with real adapters so the public
  panel shows four *real* engines — Gemini via the Google SDK **with search
  grounding** (it also stands in for Google until AIO tracking, roadmap 2b/Later),
  Perplexity via its API — each still satisfying the existing `Provider` protocol,
  with `cost_usd` from a pinned price-table constant. `DRY_RUN` is unaffected (still
  four mocks); real adapters are exercised **only** under `respx`, never a live call
  in CI (the P2.2 pattern). This is the *only* 2b work in Phase 5 — weighted score,
  2-samples, and sentiment/position stay deferred (the checker ships the honest
  binary score).
- **Why now:** a "show your work" page cannot display canned stub text under a real
  engine's name; four credible engines is the checker's headline promise vs
  Semrush. Per ADR-9 this is a single-file swap per engine.
- **Dependencies:** none beyond the P5 gate (pure providers lane); land any time.
- **Complexity:** M
- **Deliverables:** `backend/app/providers/gemini_provider.py` +
  `backend/app/providers/perplexity_provider.py` (real, replacing the stubs),
  `backend/app/providers/registry.py` (wire real when `DRY_RUN=0`),
  `backend/app/config.py` (`gemini_api_key`, `perplexity_api_key`),
  `deploy/.env.example` (`GEMINI_API_KEY`, `PERPLEXITY_API_KEY`, blank in DRY_RUN),
  ADR-23 recorded in [design.md](design.md),
  `backend/tests/pipeline/test_gemini_provider.py` +
  `test_perplexity_provider.py` (respx).
- **Acceptance:** each adapter satisfies the `Provider` protocol and passes a respx
  request/response-shape test with a computed non-zero `cost_usd`; grounding is
  enabled on the Gemini call; `DRY_RUN=1` still returns four mocks and CI makes
  **no** live provider call; `make test`/`make typecheck` green.
- **Status:** ✅ **done — session 13 (2026-07-10, commit `40d8a34`,** 0 blocking
  findings, 0 fix rounds). `gemini-2.5-flash` with the `google_search`
  grounding tool + Perplexity `sonar`, both via httpx/respx (ADR-23). Known
  honest gaps for P5.11's week-1 read: pinned prices unverified against
  vendor pages; `cost_usd` omits per-request search/grounding fees and
  Gemini thinking tokens (undercounts slightly).

### P5.8 — Turkish: native fixed prompts + suffix-aware + İ/ı-casefold footprint matching
- **Goal:** the credibility half of Turkish (2c minimal slice). Add a **native**
  (not translated) Turkish 12-prompt set to `checker_prompts.py`, selected by
  `lang='tr'` and carrying the same `VERSION` stamp + a `# NATIVE — native-speaker
  sign-off required before launch` marker. Add Turkish matching to `footprint.py`,
  gated on the run's `lang`/locale so English behaviour is byte-unchanged. Because
  the current `detect(raw_text, kyc)` signature and the `KYC` model carry **no**
  language, `detect` gains a `lang` parameter (default `'en'`) threaded from
  `analysis.lang` at its `runner.py` footprint-step call site (the checker branch
  from P5.2, same pipeline lane); `architecture.md` §2's
  `footprint.detect(raw_text, kyc)` note is reconciled in P5.11's docs pass. The two
  `lang`-gated rules: (a) the
  **dotted/dotless-i casefold** (İ/i and I/ı — the classic Turkish `.lower()` trap
  that corrupts a brand), and (b) **suffix-aware** brand/alias matching (Turkish
  agglutination — *Marka'nın*, *Markayı*, *Markada*, *Markadan* — breaks the current
  `\b`-anchored match). Validate against a small **labelled Turkish fixture** (the
  brandkit `# TODO(pipeline)` on `footprint.py`).
- **Why now:** the roadmap is emphatic that Turkish ships *at checker launch* and
  "is not the corner we cut" — wrong Turkish numbers kill the differentiation story.
  Fixed prompts make this a curated list + a matching rule, not a generation engine.
- **Dependencies:** P5.2 (the fixed-prompt module + checker branch to extend).
- **Complexity:** M
- **Deliverables:** `backend/app/pipeline/checker_prompts.py` (native TR set),
  `backend/app/pipeline/footprint.py` (TR casefold + suffix matching, gated on a new
  `lang` param), `backend/app/pipeline/runner.py` (thread `analysis.lang` into the
  footprint step; sequences after P5.2's kind-branch, same pipeline lane),
  ADR-24 recorded in [design.md](design.md),
  `backend/tests/pipeline/test_footprint_tr.py` (labelled TR precision fixture, incl.
  İ/ı cases), `backend/tests/pipeline/test_checker_prompts.py` (TR case).
- **Acceptance:** `generate(kyc, 'tr')` returns 12 non-empty native-Turkish prompts,
  version-stamped and byte-stable; the labelled fixture asserts a Turkish brand is
  matched with common suffixes and apostrophe forms, that the İ/ı casefold does not
  corrupt matches, and that unrelated tokens do **not** match; **all existing
  English `footprint` tests stay green**; `make test` green under `DRY_RUN`.
- **Status:** ⏭️ SKIPPED (operator directive 2026-07-10, post-session-12:
  English-only product). Card kept intact for a future revival; the code's
  `checker_prompts.generate` already falls back to EN for unwired langs, so
  nothing breaks. When revived, also refresh the "P5.8 wires 'tr'" comment in
  `backend/app/pipeline/checker_prompts.py`.
- **Scope reconciliation (2026-07-28, P5.14).** This card is now **smaller than
  written**, and the difference should be read before reviving it. Rule (a), the
  dotted/dotless-i casefold, **has landed** — `pipeline/textfold.py` folds `İ`→`I`
  and `ı`→`i` for every run, ungated. It shipped as step 2a of
  [discovery-kyc-improvements.md](discovery-kyc-improvements.md) on the argument
  that mishandling `İ` is a Unicode correctness bug (Python's `casefold()` turns
  it into two codepoints, which also corrupted match indices), not a Turkish
  feature — the same change fixes Nestlé and Coca-Cola. That reasoning is
  recorded rather than assumed: if the operator disagrees and wants it gated on
  `lang`, it is one module to change. **Rule (b), suffix-aware matching, was
  deliberately NOT built** and remains the deferred half, pinned by a test in
  `test_footprint.py` asserting `Yankinin` does not match `Yanki`. So a revived
  P5.8 = the native TR 12-prompt set + rule (b) + the `lang` parameter on
  `detect`; the labelled TR fixture is still owed for rule (b).

### P5.9 — Turkish UI + i18n wiring
- **Goal:** make the checker screens speak Turkish. Fill the `tr` dictionary in
  `lib/i18n.ts` with **native** copy (seeded from
  [frontend-brandkit.md](frontend-brandkit.md) §6, pending a native-speaker
  sign-off), wire the EN/TR toggle so every string on the landing, progress,
  results, and email-gate screens switches, and pass `lang` through to
  `createCheckerAnalysis`. No new dependency — the plain typed dictionary from P5.4.
- **Why now:** completes the Turkish launch requirement on the UI side; pairs with
  P5.8 so the public checker is genuinely bilingual before the loud launch.
- **Dependencies:** P5.4 (checker screens + i18n scaffold), P5.5 (email-gate copy),
  P5.8 (TR prompts, so a TR run produces sensible results).
- **Complexity:** S
- **Deliverables:** `frontend/lib/i18n.ts` (native TR dict),
  `frontend/app/checker/**` + `frontend/components/EmailGate.tsx` (toggle wiring),
  ADR-25 recorded in [design.md](design.md),
  `frontend/tests/checker-i18n.test.tsx`.
- **Acceptance:** toggling to Turkish renders all checker copy in Turkish (no
  English leakage, no untranslated keys) and a TR submit produces a TR-language run;
  the toggle is keyboard-accessible and axe-clean; `npm test -- --run` green.
  (Native-speaker sign-off is an operator step tracked in P5.11's launch gate.)
- **Status:** ⏭️ SKIPPED (operator directive 2026-07-10: English-only product).
  P5.4 therefore ships **without** the EN/TR toggle and without a `tr` dict
  placeholder — plain English strings (a typed copy module is still fine for
  tidiness, but no i18n machinery). Card kept for a future revival.

### P5.10 — Public methodology page ("show our work")
- **Goal:** the transparency wedge as a public asset. A `/methodology` page
  publishing the **12 fixed prompts** (EN + TR), the **four engines**, the **score
  formula** (`footprints / total_responses`, shown), and honest caveats: single
  sample today, binary score with the weighted 0–100 version coming, the Turkish
  matching approach and its limits. It renders the exact live prompts from a
  build-time JSON artifact **generated from** the same **version-stamped**
  `checker_prompts` module the runner reads (P5.2/P5.8) — never a hand-copy — so the
  published methodology can never drift from what actually runs. Linked from the
  checker page.
- **Why now:** roadmap 2a promises "show our work from the first touch — not a
  teaser," and the draft makes the public methodology page a headline checker
  feature and a Product-Hunt/comparison-page talking point; it is cheap (a static
  read of a generated artifact) and on-wedge.
- **Dependencies:** P5.2 **and P5.8** (the version-stamped EN+TR prompt module — the
  TR prompts come from P5.8 and are required for the both-languages render), P5.4
  (route shell + i18n seam), **P5.9** (the filled TR `i18n.ts` dict — P5.10's
  methodology copy keys layer on top, so sequence P5.9 → P5.10 to avoid an
  `i18n.ts` write collision).
- **Complexity:** S
- **Deliverables:** *(frontend half)* `frontend/app/methodology/page.tsx`,
  `frontend/lib/i18n.ts` additions, a link from `/checker`,
  `frontend/tests/methodology.test.tsx` + `methodology.a11y.test.tsx`;
  *(infra half — `scripts/**` and the `Makefile` are infra-owned, see the
  merge-risks note)* `scripts/gen_methodology.py`, the `Makefile` `gen-types`
  target wiring (+ the CI contract-drift gate picking the new artifact up), and
  `shared/contracts/checker_methodology.json` (the version-stamped fixed prompts
  **EN+TR** + score-formula/engine metadata, exported **from the `checker_prompts`
  source** so the current
  OpenAPI drift gate also guards it — a generated artifact, **never** a hand-copy;
  +lead review on `shared/contracts/**`), which the page imports at build time —
  this keeps the locked **two**-endpoint count (no new HTTP route) and mirrors the
  `openapi.json` → `types.ts` precedent from P3.1 (no frontend-lane edit of
  spine-owned `routes.py`); plus a one-line reconciliation of design.md §2's
  "two files are produced by `make gen-types`" statement (now three artifacts).
- **Acceptance:** the page renders the exact live 12 prompts (read from the
  generated `checker_methodology.json`, not a hand-copy — a prompt edit re-exported
  via `make gen-types` shows up here with **no** second edit), the formula, the
  engine list, and the stated limitations, in both languages; `make gen-types`
  produces no drift; it is axe-clean and reachable from `/checker`;
  `npm test -- --run` green.
- **Status:** ✅ **done — session 13 (2026-07-10, commits `93aa34a` +
  build-context fix `643e0ee`,** 0 blocking findings). EN-only per the
  amendment; `/methodology` renders `checker-en-v1` from the generated
  artifact (canonical `shared/contracts/checker_methodology.json` + a
  byte-identical generated copy `frontend/lib/checker_methodology.json`
  because the web Docker build context cannot reach `shared/` — caught by
  the first prod image build, fixed inline as deploy-blocking recovery);
  `make gen-types` idempotent; CI drift gate covers both copies; candid
  caveats incl. "Turkish not yet supported". *(Amendment history: EN-only —
  dependencies shrank to P5.2 + P5.4.)*

### P5.11 — Operator-gated: live 4-engine smoke, cost soak, deploy, launch gate
- **Goal:** the one live/real-key task, mirroring P4.1 + P4.2. With `DRY_RUN=0` and
  all four real keys (Anthropic + OpenAI + the new Gemini + Perplexity), run a real
  checker analysis and confirm four engines answer, footprints, the presence map,
  competitors-appeared, and a score; **capture the per-checker-run cost** and check
  it against `CHECKER_DAILY_USD_CAP` and the pricing model (feeds the roadmap 2d
  pricing decision). Verify the kill-switch, both rate limits, and the daily cost cap
  fire live. Redeploy the existing stack to `yanki.beyondkaira.com` (the `/checker` +
  `/methodology` + `/api/v1/checker*` routes need **no** edge change — the host
  nginx vhost already path-routes `/api/*` → api and everything else → web), then flip
  `CHECKER_ENABLED=1`. Add a `DRY_RUN=1` checker-happy-path e2e job to CI. The
  **loud public launch** (Product Hunt / LinkedIn) is the go/no-go gated here on:
  real engines green, the abuse guards verified live, the methodology page live, and
  **Turkish signed off by a native speaker — or the checker launches EN-only** ("no
  Turkish beats bad Turkish"). The EN-only path is a **deliberate,
  operator-authorized deviation** from the frozen roadmap **2a** "Turkish at checker
  launch (not a later add)" mandate — invoked **only** with a **named** operator
  sign-off and recorded as a deviation; the **default/primary path is bilingual at
  launch** (P5.8/P5.9 build it, so the fallback is a last resort, not the plan).
- **Why now:** cost, live-provider behaviour, and the launch decision are the only
  things `DRY_RUN` cannot prove; isolating them keeps every other task $0.
- **Dependencies:** P5.1–P5.10 all done; P4.2 deploy scripts proven.
- **Complexity:** M
- **Deliverables:** a cost + soak note (session summary / private feasibility doc),
  a `checker` e2e job in `.github/workflows/ci.yml`, a redeploy verification, the
  recorded per-run cost, a **documented demand-test metrics query** reading from
  `checker_submissions` (total demand = `count(*)` of submissions, cache-served
  hits included; fresh runs = `count(*)` of `kind='checker'` analyses; run→email
  conversion = `count(DISTINCT email)/count(*)` over submissions — per-submit
  recording means hot cached brands neither undercount demand nor lose leads; still
  a plain `count()/sum()` read, no new
  endpoint), and the docs reconciliation (architecture.md checker data-flow, roadmap
  2a status, tech-debt #2/#6 closed); no new product code unless a bug surfaces.
- **Acceptance:** a real four-engine checker run completes within the caps with no
  secret committed; the measured per-run cost **and** the demand-test metrics query
  (runs + run→email conversion) are recorded; kill-switch, both rate limits, and the
  daily cap observed firing live; `https://yanki.beyondkaira.com/checker`
  serves the loop and `/methodology` is reachable; the `DRY_RUN` checker e2e is green
  in CI; the launch go/no-go is recorded with the Turkish sign-off (or the
  named-operator-authorized EN-only deviation) attached.
- **Status:** todo — **amended 2026-07-10: the EN-only "deviation" IS now the
  operator-authorized plan** (directive recorded post-session-12, superseding
  the bilingual-default language above and in roadmap 2a). The Turkish
  sign-off gate is void; the launch go/no-go gates on: real engines green,
  abuse guards verified live, methodology page live. Dependencies shrink to
  P5.1–P5.7 + P5.10 + P5.12 done.

### P5.12 — Brandkit v2 UI refactor (added 2026-07-10, operator directive; jumps ahead of P5.4)
- **Goal:** adopt the operator's brandkit v2 ("echo" identity:
  `brandkit/brandkit/frontend-brandkit-v2.md`) across the EXISTING product
  surfaces, so the checker frontend (P5.4/P5.5) is built once on the new system.
  Port the §2 token table into `frontend/tailwind.config.ts` (teal `primary`
  `#0E7569` family, `ink`, `signal`, the `-soft`/`-strong` status shade pairs),
  swap fonts to Sora + IBM Plex Mono (self-hosted via `next/font` — no external
  font CDN), apply the v2 **score-band change** (30–59% is now `warning`, not
  `primary`) to `ScoreGauge`, and restyle the existing pages/components (home
  form, progress, results incl. KYC card + ResultsTable + expanded answers)
  token-for-token. v2 **supersedes** `docs/frontend-brandkit.md` (v1) — the
  operator's item-14 decision, now made: replace v1's §2 token table with the
  v2 values (or a pointer to the brandkit file) so no doc quotes dead indigo
  hexes; §7's a11y rules carry over unchanged.
- **Why now:** operator directive ("dive into UI refactor with given
  brandkit"); sequencing it before P5.4 avoids building the checker UI twice.
- **Dependencies:** none (frontend lane; brandkit package already in-repo).
- **Complexity:** M
- **Deliverables:** `frontend/tailwind.config.ts` (v2 tokens),
  `frontend/app/**` + `frontend/components/**` restyle (no behavior change),
  font wiring, `docs/frontend-brandkit.md` reconciled to v2, ADR in
  [design.md](design.md) (v2 adoption + the score-band semantic change),
  updated axe suites green, **manually recomputed WCAG ratios** for every
  text-on-fill pair actually used (debt #13: axe can't check contrast under
  jsdom — the brandkit's claimed ratios must be re-verified against the
  implemented combinations and recorded).
- **Acceptance:** every existing screen renders in the v2 palette/type with
  zero raw hexes in components (tokens only); `ScoreGauge` bands follow v2
  semantics (0–29 danger / 30–59 warning / 60–100 success) with the numeric
  label always present; all frontend tests + axe suites green
  (`npm test -- --run`); tsc/eslint/build green; the browser e2e in CI still
  passes (no selector/behavior drift); no backend or contract change;
  before/after screenshots of home + results attached to the session log
  (marketing gradients stay OUT of the product UI per the brandkit).
- **Status:** ✅ **done — session 13 (2026-07-10, commit `d5abee7`,** one fix
  round: the KYC `bg-ink` block). Every surface on the v2 tokens, zero raw
  hexes, Sora + IBM Plex Mono via `next/font`, v2 score bands
  (30–59% = `warning`), all 23 implemented WCAG pairs recomputed and
  recorded in `docs/frontend-brandkit.md` (repays debt #13; worst
  normal-text pair 4.62:1), CI browser e2e green (no selector drift),
  before/after screenshots in `docs/sessions/assets/2026-07-10-11/`.
  Bonus: fixed `Dockerfile.prod` baking `localhost:8141` into the Next
  rewrites (`API_ORIGIN` now a build-time env) — prod web loopback
  `/healthz` un-broken (ADR-24).

### P5.13 — Waitlist + Resend email notifications (added 2026-07-10, operator directive, session 13)
- **Goal:** lead capture ahead of launch + operator awareness of every run.
  (1) `waitlist_signups` table + `POST /api/v1/waitlist` (202 always — no
  enumeration; lowercased-unique dedupe via `INSERT … ON CONFLICT DO NOTHING
  RETURNING`; 10/IP/hour); (2) `services/emailer.py` posting to the Resend
  REST API via httpx (zero new deps), gated on `EMAILS_ENABLED` + key,
  **fail-open** — a dead email can never fail a signup or a pipeline run;
  (3) on NEW signup: thank-you to the joiner + alert to `NOTIFY_EMAIL`;
  (4) on analysis terminal status (worker): run alert with kind/score/link —
  runs remain **recorded** in `analyses`; the mail is the alert, not the
  record; (5) home-page `WaitlistForm` on the v2 tokens.
- **Why now:** operator directive mid-session-13 ("add a waitlist with
  resend api… send thank you + notify info@… notify on demo runs").
- **Dependencies:** none (additive); Resend delivery gated on the operator's
  domain verification (operator-expected B1).
- **Complexity:** M
- **Deliverables/acceptance:** as built — see ADR-25; respx-only tests
  (emailer resilience, endpoint, worker hook), live-proven 202/202-dup/422.
- **Status:** ✅ **done — session 13 (2026-07-10, commit `c521931`,** two
  workflow runs: the first run's green code was lost uncommitted to a
  concurrent workflow's scope-enforcing fixer — see the session log's
  workflow-ops note — and was re-implemented cleanly, 0 fix rounds).
  Backend 170 + frontend 58 tests. **Ops note:** emails deliver only after
  the operator verifies a Resend sending domain (testing mode: account
  email only); `EMAILS_ENABLED=1` set in prod env at the session-13 deploy.

### P5.14 — Discovery + KYC input quality (added 2026-07-28, session 14)
- **Goal:** fix the *input* side of "make the number trustworthy". Five of the
  six steps in [discovery-kyc-improvements.md](discovery-kyc-improvements.md):
  (1) parse `application/ld+json` instead of letting `_clean_text` throw it away;
  (2a) fold diacritics and treat hyphen/space as interchangeable in
  `footprint.detect`, and mint ASCII-folded + legal-suffix-stripped aliases;
  (3) repair a prose-wrapped KYC response, then **one** bounded retry;
  (4) guard `_fetch` on Content-Type and size; (5) `kyc.require_usable` refuses
  the `execute` fan-out on a profile with no company or no topic.
- **Why now:** these two steps feed everything after them — `prompts.py` writes
  questions from the KYC profile, and `kyc.company` + `kyc.aliases` *are* what
  `footprint.detect` counts. Bad input here never raises; it returns a
  plausible-looking GEO score that is quietly wrong, which is the exact failure
  mode roadmap 2b exists to eliminate.
- **Dependencies:** none (all additive to existing pipeline modules).
- **Complexity:** M
- **Deliverables:** `backend/app/pipeline/discovery.py` (JSON-LD pass,
  Content-Type/size guard), `backend/app/pipeline/textfold.py` (**new** — the
  shared 1:1 ASCII fold), `backend/app/pipeline/footprint.py` (folded,
  separator-tolerant matching), `backend/app/pipeline/kyc.py` (alias minting,
  parse repair + retry, `require_usable`), `backend/app/pipeline/runner.py`
  (the gate), tests in `test_discovery.py` / `test_footprint.py` /
  `test_kyc.py` / `test_runner.py` / `test_textfold.py` (**new**), ADR-26 in
  [design.md](design.md).
- **Acceptance:** one commit per step, each leaving the repo runnable; backend
  + frontend suites green; `make gen-types` a **zero diff** (no Pydantic schema
  touched, no migration, no `checker_prompts.VERSION` bump); a test asserts the
  step-2a/2b boundary holds (suffixation still does **not** match).
- **Status:** ✅ **done — session 14 (2026-07-28)**, six commits on
  `feat/discovery-kyc-improvements` (`cf28cbc`, `f25462d`, `8ce7356`,
  `c74ccd3`, `8337045`, `684108a`), shipped via
  [PR #10](https://github.com/Beyond-Kaira/yanki-mvp/pull/10) with the docs
  reconciliation commits that followed. Backend 236 passed / 3 skipped
  (Postgres-gated), frontend 68 passed, ruff + mypy clean. **Steps 2b and 6 of
  the document are deliberately NOT built** — they revive §2c scope parked by
  operator decision; see operator-expected **A2** and tech-debt #29.

### P5.15 — Pipeline quality: crawl fidelity, grounded profiles, question realism (added 2026-08-01, session 15)
- **Goal:** take discovery, KYC and prompt generation from MVP plumbing to a
  measurement instrument, per [pipeline-quality-plan.md](pipeline-quality-plan.md):
  **D** decode by the declared charset, sniff binary, retry the homepage once,
  score links instead of substring-matching them, read each block of copy once;
  **K** sanitize every field, ground proper nouns against the crawl, add
  `category` + `use_cases`, repair-prompt the single retry; **P** filter topics
  that cannot be a category, phrase by topic kind and number, rotate over every
  topic × shape pair, and never name the brand in a scored question.
- **Why now:** ADR-26 fixed *how much* of a site we read and whether the KYC
  call survives a formatting slip. It did not address wrong *content* — an
  invented product, an alias that was never on the site (which inflates the GEO
  score, because `footprint` cannot tell it from a real mention), or a "keyword"
  that is a spec attribute and becomes a question nobody asks.
- **Dependencies:** P5.14 (builds on `textfold`, the parse/retry path and the
  usability gate).
- **Complexity:** L
- **Deliverables:** `backend/app/pipeline/sanitize.py` (**new**),
  `discovery.py`, `kyc.py`, `prompts.py`, `checker_prompts.py`, `runner.py`,
  `providers/mock.py`, `frontend/lib/contracts.ts`, `frontend/components/KycCard.tsx`,
  tests in `test_sanitize.py` (**new**) / `test_discovery.py` / `test_kyc.py` /
  `test_prompts.py` / `test_checker_prompts.py` / `KycCard.test.tsx`, ADR-27 in
  [design.md](design.md), tech-debt #30–#33.
- **Acceptance:** backend + frontend suites green; `make gen-types` a **zero
  diff**; `checker_prompts.VERSION` unchanged and the published methodology
  prompts byte-identical (pinned by a test); no new paid provider call on any
  path; a test proves a brand in the keywords never reaches a scored question.
- **Status:** ✅ **done — session 15 (2026-08-01)** on
  `feat/pipeline-quality-production-grade`. Steps 2b and 6 of
  `discovery-kyc-improvements.md` remain **not built** (operator item A2); this
  work is language-neutral and does not touch that decision.

### P5.16 — SERP visibility from an open-source metasearch instance (added 2026-08-03, session 16)
- **Goal:** measure the *organic* search surface alongside the AI-answer GEO
  score — whether the company also shows up in ordinary search results for
  brand-free buyer queries. The source is a self-hostable **SearXNG** instance
  (AGPL-3.0) read over its JSON API, chosen over a paid SERP API (a per-query
  bill in front of the pricing wedge) and over scraping the engines directly
  (a maintenance treadmill). It runs **inside the footprint step**, not as a
  seventh one, and is **off by default**. Per ADR-28.
- **Why now:** the GEO score measures one surface — what AI engines say. Buyers
  still use the other one, and [roadmap.md](roadmap.md) named the gap out loud
  ("Google AI Overviews tracking … our biggest admitted gap vs Semrush; needs
  SERP scraping or a paid SERP API"). SearXNG is a third option that sentence
  predates: it puts the public engines behind one self-hostable JSON API for
  $0, closing the *organic* half of the gap. The AI Overviews box itself has no
  $0 source and stays open (roadmap Later).
- **Dependencies:** ADR-27's brand-leak invariant — SERP query generation
  reuses `prompts.topic_pool` and re-checks each finished query with
  `prompts.leaks_brand` (`_brand_keys`/`_leaks_brand` made public for this
  rather than copied) so no scored query can name the brand. Additive to the
  existing pipeline otherwise.
- **Complexity:** L
- **Deliverables:** `backend/app/serp/` (**new** package — `base.py`
  (`SerpSource` protocol, `SerpResult`/`SerpPage`, `SerpUnavailable`),
  `searxng.py`, `mock.py`, `registry.py`);
  `backend/app/pipeline/serp_visibility.py` (**new** — brand-free query
  generation, hit detection, scoring and the run pass, all inside the footprint
  step); `prompts.py` (`_brand_keys`/`_leaks_brand` made public as
  `brand_keys`/`leaks_brand`); `backend/app/db/models.py` (**new** `SerpCheck`
  model / table `serp_checks`, one row per query, plus five nullable `serp_*`
  columns on `analyses`); `backend/alembic/versions/0007_serp_visibility.py`
  (**new**, additive); `backend/app/api/schemas.py` + `routes.py` (nullable
  `serp` object — `SerpVisibilityOut` / `SerpCheckOut`); `backend/app/config.py`
  (nine `serp_*` settings, `serp_enabled` default **False**);
  `frontend/components/SerpVisibility.tsx` (**new**, rendered on **both** results
  pages) + `frontend/lib/contracts.ts` aliases; tests in `backend/tests/serp/`
  (**new**) / `test_serp_visibility.py` (**new**) / `test_runner.py` /
  `test_api.py` / `SerpVisibility.test.tsx` + `.a11y.test.tsx` (**new**), plus a
  **new** `backend/tests/integration/` tier against a real SearXNG (skipped
  unless `SERP_TEST_BASE_URL` is set, so `make test` stays hermetic);
  `.github/workflows/serp.yml` (**new** `SERP` workflow — four jobs: real-SearXNG
  integration, scheduled upstream-drift on `:latest`, alembic up **and** down on
  Postgres, one whole analysis through the DRY_RUN compose stack) +
  `.github/scripts/`; `SERP` added to `notify.yml`'s `workflows:`; ADR-28 in
  [design.md](design.md).
- **Acceptance:** backend + frontend suites green; `make gen-types` a **real
  diff** this time (`openapi.json` + `types.ts` gain the nullable `serp`
  object); migration `0007` applies **and reverts** on Postgres;
  `checker_methodology.json` untouched; the three distinct nulls preserved and
  asserted (`serp` absent = never measured, `serp.score` null = we looked and
  could not read, `0.0` = read and found nothing); unmeasurable pages dropped
  from the denominator, never counted as misses; `run_serp` never raises (an
  instance being down costs the run its SERP number and nothing else);
  `SERP_ENABLED` defaults **False** so an existing deployment is unchanged until
  an operator flips it and stands up an instance.
- **Status:** ✅ **done — session 16 (2026-08-03)** on `feat/serp-visibility`.
  Backend 382 passed / 7 skipped (the new SERP integration tier, which needs a
  live instance), frontend 79 passed. **Not built, deliberately:** Google AI
  Overviews tracking (the AI answer box itself — no $0 source yet, still roadmap
  Later), a weighted / position-aware SERP score, scheduled re-measurement over
  time, and a production SearXNG instance (an operator action, recorded in
  [operator-expected.md](operator-expected.md)).

### P5.17 — Stand up the SearXNG instance and enable SERP in production (added 2026-08-03, session 17)
- **Goal:** turn the SERP feature on. ADR-28 shipped the code but left the
  instance unbuilt; this stands one up as a **profile-gated compose service** in
  both the prod and dev compose files, pins and resource-caps it, adds the
  gitignored host-config arrangement `deploy/.env` already uses, and flips the
  three env lines that make the worker read it. It is infrastructure, not a
  feature change: no pipeline, provider, scoring or UI code is touched. Per
  ADR-29.
- **Why now:** ADR-28 deliberately deferred the instance — standing one up
  spends real resources on a VPS shared with four other production tenants, and
  that spend is the operator's call, not engineering's. The operator made the
  call the same day (operator-expected **B6**): turn it on. It earns its own
  record because measuring the instance first changed several of its parameters
  (which engines to keep, the memory cap, and the per-query intermittency
  finding).
- **Dependencies:** P5.16 / ADR-28 (the SERP feature this instance feeds — the
  worker already reads `SERP_BASE_URL` and is fail-open) and the operator's
  **B6** decision. No code dependency beyond that.
- **Complexity:** M
- **Deliverables:** the `searxng` service in `deploy/docker-compose.prod.yml`
  and `deploy/docker-compose.yml`, behind the **`serp` profile** so it starts
  only when `deploy/.env` sets `COMPOSE_PROFILES=serp` — compose reads that from
  the project-directory env file, so there is **no change to `deployment.sh`**;
  image pinned `searxng/searxng:2026.8.1-8892414dc`; `mem_limit: 512m` /
  `cpus: 0.5` / bounded json-file logs; **prod publishes no port** (only
  `api`/`worker` reach it at `http://searxng:8080`, which is what lets its
  limiter stay off) while **dev publishes a loopback** `YANKI_SEARXNG_PORT`
  (default 8144) for debugging; deliberately **not** a `depends_on`, because the
  SERP pass is fail-open. `deploy/searxng/settings.example.yml` (**new**,
  tracked — only the four real web-search engines kept (`google cse`,
  `duckduckgo`, `brave`, `startpage`), the six default widget engines dropped,
  limiter off, JSON format on, the low-entropy `ultrasecretkey` placeholder);
  `.gitignore` (ignore the host `deploy/searxng/settings.yml`, track only the
  example); `deploy/.env.example` (the `COMPOSE_PROFILES` opt-in note plus the
  `SERP_BASE_URL=http://searxng:8080` bundled value); ADR-29 in
  [design.md](design.md); tech-debt **#43** and **#44**. Host-side, not in the
  repo (operator action): the real `deploy/searxng/settings.yml` with a
  generated `secret_key`, symlinked into the auto-deploy checkout exactly as
  `deploy/.env` is, and the three `deploy/.env` lines `COMPOSE_PROFILES=serp` /
  `SERP_ENABLED=1` / `SERP_BASE_URL=http://searxng:8080`.
- **Acceptance:** `deploy/searxng/settings.yml` stays gitignored (the real key
  never enters the public history CI scans); production runs a fifth container
  at a measured ~105–150 MiB steady state, capped at 512 MiB; SERP is live and
  reads real results (Salesforce 4/4, HubSpot 4/4, Baykar 3/4 on their own
  categories, ~0.5 s median per query; 8/8 buyer-style queries measurable at
  20–30 results each); `unresponsive_engines` is non-empty on most stored rows —
  accurate reporting, not a fault, because two of the four engines are usually
  refused from this egress IP; turning SERP on costs no `deployment.sh` change,
  and any deployment that has not set `COMPOSE_PROFILES=serp` never creates the
  container.
- **Status:** ✅ **done — session 17 (2026-08-03)** on `feat/serp-instance`.
  **Not shipped, deliberately:** any change to the SERP feature code itself, a
  weighted / position-aware SERP score, scheduled re-measurement over time, and
  Google AI Overviews tracking (still no $0 source, roadmap Later). Two new
  tech-debt items: **#43** (DRY_RUN forces the mock SERP source, so the real
  SERP path cannot be rehearsed with a mocked LLM panel) and **#44** (two of the
  four engines refused per query, so the score leans on `google cse` more than a
  four-engine panel suggests).

---

### Phase-5 assumptions
- **Reusing `analyses` for checker rows is the right call** (a `kind` column, not a
  new `checker_analyses` table): the checker walks the identical queue + six-step
  lifecycle, so a parallel table would duplicate the worker, the GET envelope, and
  every model. Recorded as **ADR-19** when built.
- **The worker needs no dispatch change.** The `kind`-branch lives inside
  `run_pipeline` (pipeline lane), so `app/worker.py` calls it unchanged — no
  separate `checker_runner`, no worker seam. This is deliberately more minimal than
  a parallel runner and removes a backend-spine ↔ pipeline merge risk.
- **KYC is reused as-is, not synthesized.** Running the existing KYC step on the
  seed string is zero new code and keeps the DRY_RUN score coherent (~0.5, about
  "Yanki Demo Co" per tech-debt #3); the real brand is shown under real keys. A
  brand-derived "KYC-lite" was rejected (see the preamble) because under DRY_RUN it
  collapses the score to ~0.
- **Lead capture and demand counting are per-submit, not per-analysis-row.** The
  append-only `checker_submissions` table exists because the 24h cache shares one
  `analyses` row across many visitors: a single `analyses.email` column would let
  visitor B's email overwrite visitor A's on a hot cached brand (losing exactly
  the leads the checker exists to capture), and `count(*)` over `analyses` would
  miss every cache-served demand signal. One submission row per accepted submit
  (email nullable until the gate is filled) fixes both; the lead list is
  `SELECT email FROM checker_submissions WHERE email IS NOT NULL`. Richer lead
  metadata (consent flags, dedupe) can be added to this table later if marketing
  needs it.
- **Competitors are computed from the raw answers**, via a deterministic Title-Case
  proper-noun co-mention heuristic (brand + aliases excluded, stoplist-filtered),
  **not** from `kyc.competitors` and **not** via an LLM pass. This is $0,
  deterministic, and faithful to "brands that showed up" (it surfaces brands the KYC
  list never knew). Recorded as **ADR-21**.
- **Checker KYC leans on model world-knowledge**, not a crawl: with only
  brand+category as seed text, the KYC call infers aliases from what the model knows
  about the brand. Acceptable for a free checker, and the "show your work" ethos
  means we display exactly what came back.
- **One worker suffices for the demand-test volume** (~3000 runs / 90 days ≈ 33/day);
  the `llm_cache` upsert (P5.2) removes the tech-debt #6 race so a second worker can
  be added later with no code change.
- **`ip_hash` is a salted hash of the `X-Forwarded-For` client IP** (privacy behind
  the nginx edge), stored instead of a raw IP; the salt (`RATE_LIMIT_SALT`) is a
  new env var.
- **`CHECKER_ENABLED` defaults to `0`** — the public route is dark in every
  environment (`deploy/.env.example` ships `0`) until the operator flips it at
  P5.11; local dev and the CI e2e job set it `1`.
- **A plain typed i18n dictionary** (no `next-intl`) is enough for a two-language,
  handful-of-screens surface — fewer moving parts. Recorded as **ADR-25**.
- **12 fixed prompts × 4 engines = 48 responses** fits under the existing
  `MAX_RESPONSES_PER_JOB=60`, so no cost-cap or queue change is needed; **12** is a
  constant, not a configurable knob.
- **The binary score is an acceptable, honest ship for the free checker** — the
  weighted 0–100 score (2b) is deferred and the methodology page (P5.10) says so.
- **The fixed prompt sets are version-stamped** so the runner and the methodology
  page read one identical, published source.

### Phase-5 open questions (operator input wanted)
- **Native Turkish prompts + copy need a native-speaker sign-off** before the loud
  launch (brandkit §6 / roadmap 2c risk). **Who signs off — and who is the named
  operator authorized to invoke the EN-only fallback?** Resolve this owner **early**
  so the primary path (bilingual at launch) stays the default. Confirmed launch
  rule: if no sign-off by go-live, the checker launches **EN-only** — a **deliberate,
  recorded deviation** from the frozen roadmap 2a "Turkish at checker launch (not a
  later add)" mandate — and Turkish follows once signed off (P5.8/P5.9 build it;
  P5.11 gates the launch on it).
- **Default abuse thresholds are guesses:** `CHECKER_RATE_LIMIT_PER_IP_HOUR=5`,
  `CHECKER_RATE_LIMIT_PER_BRAND_DAY=3`, and `CHECKER_DAILY_USD_CAP=50` — the real
  numbers come from P5.11's Week-1 cost read and the pricing decision. Product to
  confirm the free-tier generosity vs spend.
- **Behind-proxy client IP:** rate limiting keys on a salted hash of the client IP;
  behind the host nginx edge the real client IP arrives via `X-Forwarded-For` — confirm
  the trusted-proxy handling so the hash keys on the visitor, not the proxy, and is
  spoof-resistant enough for per-IP limiting. (Infra detail for P5.6/P5.11.)
- **Which brand gets the "≥1 full raw answer" shown free** — defaulting to the first
  answer that mentions the brand (falling back to the first answer) unless product
  prefers a "best" one. Affects the `EmailGate` framing in P5.5.
- **Competitor precision on real answers:** the deterministic proper-noun heuristic
  is $0 and faithful on the mock, but can be noisy on real answers. If it proves
  thin/noisy after P5.11's read, the fallback is one cheap "extract the brands
  mentioned" LLM pass (pulling a small slice of 2b's extraction forward) — deferred
  unless the data demands it.
- **Where the checker lives / email gate strength / captcha:** `/checker` on the
  same origin is assumed; a single unverified email is assumed for max lead capture
  (weakest abuse control). Whether to add email verification, disposable-domain
  blocking, or a lightweight proof-of-work/captcha before go-live is a product/abuse
  trade-off to confirm at P5.11.
- **Grounding cost/ToS:** Gemini search grounding and Perplexity live-search add
  cost and have ToS constraints (the draft flags a "ToS review for all 4 APIs");
  confirm grounding is on and compliant before P5.7's live path runs in P5.11.

---

## Phase 6 — Accounts (roadmap 2d)

*The first post-MVP phase. Roadmap [§2d](roadmap.md) is "auth, accounts,
projects + onboarding wizard"; these cards cover only the auth slice of it.
**Both cards are written retroactively** — the work was built before it had
tickets — so they record what shipped rather than what was planned. Numbering
starts a new phase deliberately: Phase 5 is the free public checker (roadmap
2a) and this is not part of it.*

### P6.0 — Auth endpoints: signup / login / refresh / logout / me (PR #9)
- **Goal:** email + password accounts behind a short-lived bearer token paired
  with an httpOnly, single-use refresh cookie.
- **Why now:** every §2d feature (saved analyses, projects, cadence) needs to
  know who is asking.
- **Dependencies:** none.
- **Complexity:** M
- **Deliverables:** `backend/app/api/auth_routes.py`,
  `auth_cookies.py`, `auth_dependencies.py`, `app/services/auth.py`,
  `app/services/auth_sessions.py`, `alembic/versions/0006_auth_sessions.py`,
  `tests/test_auth_api.py` / `test_auth_service.py` / `test_auth_sessions.py`.
- **Acceptance:** signup returns 201 and **no session**; login returns the user
  plus a bearer and sets the refresh cookie; refresh rotates single-use and
  revokes the whole family on replay; logout clears the cookie; `/me` needs the
  bearer.
- **Status:** ✅ **done — PR #9**, merged before this phase existed as a card.
  Documented here in arrears; the session note for it is
  `sessions/2026-07-28-01.md`, which is a stub.

### P6.1 — Account screens + the browser session layer (PR #13)
- **Goal:** the screens for P6.0 — sign up, log in, log out, a header that
  reflects the session — plus the client-side session layer they need: the
  access token in memory, rotation of the refresh cookie, and a 401 that
  refreshes once and replays.
- **Why now:** the endpoints exist and nothing reaches them.
- **Dependencies:** P6.0.
- **Complexity:** M
- **Deliverables:** `frontend/app/{signup,login}/page.tsx`,
  `frontend/components/{AuthProvider,SiteHeader,CustomFormField,CustomPasswordField,CustomFormError}.tsx`,
  `frontend/lib/{session,auth,validation}.ts`, `lib/api.ts` (`authorizedFetch`),
  `lib/contracts.ts` (`AuthUser`, `Credentials`, `SignupCredentials`,
  `LoginResponse`), tests in `tests/{auth,session}.test.ts`,
  `tests/{LoginPage,SignupPage,SiteHeader}.test.tsx` and
  `tests/{LoginPage,SignupPage}.a11y.test.tsx`, **ADR-32** in
  [design.md](design.md).
- **Acceptance:** a reload keeps the session by rotating the cookie; the bearer
  is never persisted anywhere a script can read it; concurrent refreshes — in
  one tab and **across tabs** — produce exactly one rotation; a 401 refreshes
  once and replays the original request; every field error is announced; no
  screen ships a control the API cannot honour.
- **Status:** ✅ **done — merged 2026-08-03**
  ([PR #13](https://github.com/Beyond-Kaira/yanki-mvp/pull/13); recorded
  post-hoc in session 20 — the merge happened outside a session). The session-19
  review response held: all nine items answered
  (`sessions/2026-08-03-04.md` §1); **password reset and the terms checkbox
  were deliberately removed rather than shipped** (tech-debt #49/#50, both now
  scheduled for repayment inside Phase 7 — P7.5 and P7.6's terms dependency).
  Tech-debt #52 (an account grants nothing) is now answered by the roadmap
  itself: the first signed-in destination is the M1 org admin (P7.4).

---

## Phase 7 — Admin Platform (roadmap M1) — CURRENT PRIORITY

*Spec: [admin-panel-plan.md](admin-panel-plan.md) (scope authority for this
phase) · product frame: [roadmap.md](roadmap.md) M1 · target seams:
[architecture-target.md](architecture-target.md). Cards below are
**planning-level stages (A1–A9)**; each is decomposed into session-sized
sub-cards at build time, per the doc's §9. No card starts before the
operator ratifies the roadmap (operator-expected **A3**) and the **B7** key
check clears — both cleared 2026-08-05.*

*Status as of 2026-08-05 (session 22): **A1–A4 are done** (P7.1 tenancy, P7.2
RBAC, P7.3 audit spine, P7.4 Admin Panel v1). A5–A9 are open. The statuses
below were stale for a session — P7.2 and P7.3 shipped in session 21 while
their cards still read "todo" — so treat a card's status line, not this
paragraph, as the record.*

### P7.1 — Tenancy schema + personal-org backfill (stage A1)
- **Goal:** organizations → workspaces → projects exist; every existing row
  (users, analyses, seo_projects, checker/geo data) lands in a personal org;
  reads are org-scoped at the data layer.
- **Why now:** the riskiest migration, cheapest while the surface is small;
  every later milestone consumes it.
- **Dependencies:** A3 ratification; staging rehearsal of the backfill.
- **Complexity:** L · **Status: DONE** (2026-08-05, session 21, ADR-35).
- **As built** — three deviations from the §8 sketch, each deliberate:
  (a) a generic `projects` table WAS created and backfilled 1:1 from
  `seo_projects`, which keeps its own identity rather than being renamed;
  (b) `analyses` gains **`org_id` only** — nullable, no FK, no index — because
  NULL is the *public* scope and the FK's delete rule would have to be
  `RESTRICT` (a `SET NULL` would republish a deleted org's private analyses);
  (c) child tables (`site_audits`, `responses`, `geo_records`, …) get **no**
  denormalized `org_id` — they are reachable only through org-scoped parents,
  so the join is the isolation. Postgres RLS deferred. Verified up/down/up on
  Postgres with seeded colliding-slug data.
  **Corrected 2026-08-08 (session 24):** this card originally read "scoping is
  a fail-closed service-layer seam." It is not. `scoped()` and
  `readable_analysis()` were written but are called by nothing; isolation is
  enforced per-route via the `requires(...)`/`OrgContext` dependency, which
  works but does not fail closed when a route forgets to filter. See the
  correction on ADR-35 in [design.md](design.md) and tech-debt **#63**.
- **Acceptance:** additive migrations up+down clean; every pre-existing row
  reachable through exactly one org; zero behaviour change for anonymous
  flows; cross-org read attempts fail in tests.

### P7.2 — RBAC: roles, permissions, API-layer enforcement (stage A2)
- **Goal:** the ten-role model (Super Admin → Guest) with resource-based
  permissions (`resource:action`), deny-by-default, enforced as FastAPI
  dependencies; permission test suite generated from the baseline §11.2
  matrix.
- **Dependencies:** P7.1. · **Complexity:** L · **Status: DONE** (2026-08-05,
  session 21).
- **As built:** ten roles and thirty `resource:action` permissions in
  `services/permissions.py`, enforced by a single `requires(permission)` route
  dependency that **denies by default and audits the refusal**. Three
  properties the tests pin: an unknown role, an unknown permission and a
  missing context all return False; Guest is built up from nothing rather than
  derived from Viewer, so a permission added to Viewer cannot leak into the
  client lane; and a second independent `CLIENT_FORBIDDEN` check catches a
  well-meaning refactor of the grants.
- **Residual:** scope grants are org-grain only. Workspace-scoped roles exist
  as strings and are honoured as org-level capabilities — per-workspace
  narrowing is A9's follow-up, not shipped.

### P7.3 — Audit-event spine (stage A3)
- **Goal:** append-only `audit_events` with actor/org/entity/before/after/
  ip_hash/outcome, emitted from auth + every mutating route; secret-redacted
  diffs.
- **Dependencies:** P7.1. · **Complexity:** M · **Status: DONE** (2026-08-05,
  sessions 21 + 22; ADR-38, ADR-39).
- **As built:** the store and redaction landed in session 21; session 22 closed
  the three gaps that made it unusable as evidence. (a) `request_id`, `ip_hash`
  and `user_agent` were NULL on every row and are now filled from a
  `ContextVar` set by middleware (ADR-39). (b) auth events carried **no
  organization**, so the sign-in trail was invisible to the org-scoped query
  that reads it; signup and login are now attributed, including a failed login
  for a known address. (c) tamper evidence: a per-row `record_hash` plus a
  Postgres trigger refusing UPDATE and DELETE (ADR-38).
- **Residual:** `emit` still swallows its own errors, so a failed audit write
  loses the event rather than the request. Hardening that into an outbox is
  A9's, and it is the one thing here that is a trade rather than a fix.

### P7.4 — Admin Panel v1 (stage A4)
- **Goal:** the first signed-in destination: org/member/invitation/audit
  screens (repays the product half of tech-debt #52).
- **Dependencies:** P7.2. · **Complexity:** M · **Status: DONE** (2026-08-05,
  session 22; ADR-37).
- **As built:** `/admin` is a top-level nav section named **Admin Panel** with
  three tabs — Members & roles, Invitations, Audit log — rather than a leaf
  buried under Settings. Members: search/filter/page, assign and change roles,
  disable and re-enable, and **remove a seat** (the membership, never the
  account), each guarded against the two lockout paths and each audited with
  before/after. Invitations: hashed single-use expiring tokens, resend (which
  rotates the token), withdraw, and a public `/invite/<token>` accept flow that
  creates the account and signs the invitee in (ADR-37). Audit log: filter,
  search, sort, page, per-record history, before/after diffs, and an integrity
  report.
- **Not in v1:** workspace management screens, and the organization profile is
  read-only. Both are A9/M6 work; naming them here keeps the card honest.

### P7.5 — Auth completion: password reset, MFA, sessions (stage A5)
- **Goal:** password-reset endpoint + restored screen (repays #49;
  enumeration-safe), TOTP MFA with backup codes, device/session list with
  remote revoke, org-level require-MFA policy.
- **Dependencies:** P7.2 (policy), P7.3 (events). · **Complexity:** M ·
  **Status:** **partial — the migration-free half shipped 2026-08-08 (session
  24)**, merged as `ddf3167` (PR #40) and live in production.

  **Done (no schema change — reuses the `AuthSession` family model from
  migration 0006):** `GET /auth/sessions`, `DELETE /auth/sessions/{id}`,
  `POST /auth/sessions/revoke-all`, all three self-scoped and audited; a
  "Devices & sessions" section in `/settings`; the caller's full organization
  list added **additively** to `/auth/me`; and an org switcher in the app shell
  that sends `X-Org-Id`. That last piece closes a real defect invitations
  opened in session 22: a user could hold two memberships while
  `resolve_org_context` silently picked `memberships[0]`, so an accepted
  invitation to a second org was **unreachable**. Note the frontend had never
  sent `X-Org-Id` at all — the seam was honoured server-side and no client code
  carried it. See ADR-43.

  **Deferred, deliberately — every remaining piece needs a migration:**
  password reset (#49), TOTP MFA with backup codes, and the org require-MFA
  policy. They wait on **database backups** (operator item), because A5–A8 each
  add a live migration to a database with no backup and rollback restores the
  image, never the data. The dead `requestPasswordReset()` stub in
  `frontend/lib/auth.ts` was left in place as the contract the endpoint must
  meet. Residual debt: #67 (no device fingerprint without a migration), #68
  (stale active-org self-heals only on `/auth/me`), #69 (`/auth/me` N+1).

  **The password policy shipped ahead of the rest, 2026-08-19, on
  `feat/strong-password-check` — it needed no migration.** The whole rule had
  been `min_length=8` on two schemas; it is now `services/password_policy.py`:
  twelve characters, a leet-folding blocklist of the passwords people actually
  pick (with a Turkish section, because the users are), a rule against building
  a password out of your own address or organization name, pattern and
  keyboard-run rules, NFKC normalization paired across hash and verify, and an
  advisory strength meter on both screens. No character-class requirement —
  800-63B forbids one, and the score gates nothing for the same reason. See
  **ADR-50**. On the invitation path the policy gates only
  the branch that creates an account, because a signed-in invitee keeps the
  password they already have. New debt: #93 (existing weak passwords are unreachable
  until #49 gives them somewhere to go), #94 (the blocklist is a curated head,
  and the HIBP check is deferred to A5 where the plan already schedules it),
  #95 (two maximum-length numbers), #96 (the frontend policy is a mirror).

### P7.6 — Plans, subscriptions, quotas, credit ledger (stage A6)
- **Goal:** plan catalog as data; Stripe subscription lifecycle; quota
  service enforced on submission paths; credit ledger seeded from existing
  `cost_usd`; terms text is a hard dependency (tech-debt #50 — operator/legal).
- **Dependencies:** P7.1–P7.3; Stripe account (operator). · **Complexity:** L
  · **Status:** **partial** — corrected 2026-08-08 (session 24) after reading
  the code. `todo` was wrong and wrong in the expensive direction: **the
  foundation is built.** Migration `0015_billing` created `plans`,
  `subscriptions`, `credit_ledger` and `usage_counters`; `0016_seed_plans`
  seeds a five-tier catalog (free/starter/pro/business/enterprise) as data, in
  a migration rather than a startup hook; and the quota + credit service
  (`check_quota` / `consume_quota` / `reserve` / `settle` / `record_charge`)
  is complete. **What is missing is enforcement, not machinery.** The three
  live spend paths — analysis submit, checker, site-audit submit — carry no
  quota check at all, and the only metered caller is the backlink refresh path,
  which is dark behind `BACKLINKS_ENABLED`. No `Subscription` row is ever
  created, so every org silently falls back to Free and **every plan tier is
  decorative today**. Remaining: wire the gate onto the three spend paths
  (`enforce-quota-on-spend-paths`), the Stripe lifecycle, and a billing
  visibility API. The Stripe half stays blocked on the operator (account +
  terms text, tech-debt #50); **the enforcement half is not blocked by
  anything** and is the highest-value unblocked card in Phase 7.

  **Enforcement half DONE 2026-08-09 (session 25, ADR-45).** Plan tiers are no
  longer decorative. What shipped:

  - **`POST /api/v1/analyses` now requires authentication** and `analysis:run`,
    and stamps `org_id` on the row. It had been open since the MVP; session 21
    moved the URL form behind sign-in and nobody closed the route, so **every
    analysis a customer ran was attributed to no tenant**. That, not the missing
    `consume_quota` call, was the real blocker — a quota needs a tenant.
  - **`GET /api/v1/analyses/{id}` is scoped through `tenancy.readable_analysis`**,
    which had zero call sites (tech-debt #63, partially repaid). Org-less rows
    stay world-readable on their id; an org's rows are that org's alone.
  - **Three allowances enforced**: `analyses` and `site_audits` as monthly flows,
    `projects` as a **stock** (rows held, not rows created — a monthly counter
    would let Free hold twelve projects by December). New
    `billing.check_stock_quota`.
  - **`PlanCatalogMissing`** separates "this deployment has no plan catalog"
    (503) from "you are out of quota" (429). `limit_for` used to answer both
    with `0`.
  - **App-level exception handlers** in `api/main.py` map `QuotaExceeded` → 429
    with `metric`/`used`/`limit`, `InsufficientCredit` → 402,
    `PlanCatalogMissing` → 503, so no future metered route can forget.
  - **The worker settles each run's real cost** into the credit ledger, on
    success and on failure, idempotently. Per-org spend is visible for the first
    time — the input P7.8's rollups need.
  - **`QUOTA_ENFORCEMENT_ENABLED`** (default **on**) and
    **`scripts/set_org_plan.py`**, because enforcement without a way to change a
    tier is a cage with no key. There is no Stripe lifecycle and no back office.

  **The checker is deliberately capped rather than metered** — it is anonymous,
  so there is no org to charge, and billing a signed-in caller for the free
  public tool would be wrong. Its bound stays global: `CHECKER_ENABLED`, the
  IP/brand rate limits, and `CHECKER_DAILY_USD_CAP`. Recorded in ADR-45 rather
  than left as an unexplained gap.

  **Still open in A6:** the Stripe subscription lifecycle and the billing
  visibility API (invoices, ledger, spend-by-workspace), both still blocked on
  the operator's Stripe account + terms text; and granting each plan's
  `monthly_credit_usd`, without which `reserve()`'s credit gate can never pass
  and so is used nowhere but the dark backlink path.

### P7.7 — Platform back office (stage A7)
- **Goal:** Super Admin/Support surface: org directory, plan overrides,
  feature flags (global + per-org), audit-log viewer, logged impersonation.
- **Dependencies:** P7.2, P7.3. · **Complexity:** M · **Status:** todo

### P7.8 — System pages: jobs, queues, providers, health, usage (stage A8)
- **Goal:** operational visibility — job/queue boards with retry/cancel,
  AI-provider status (keys present, models, pinned prices, spend rollups,
  geo_mode/DRY_RUN visibility), health probes, usage analytics, error
  tracking wiring.
- **Dependencies:** P7.3 (events), P7.6 (spend data). · **Complexity:** M ·
  **Status:** **partial** — the *health* slice landed 2026-08-09 (session 25,
  ADR-47), out of order, because it was also the last of the backlog's P0 band
  and because it was a live defect rather than a missing page: `/healthz`
  returned a hardcoded literal and **is the deploy gate**, so a release with an
  unreachable database answered healthy and was recorded as `.last-good`. It is
  now a readiness probe over six components (database, schema revision, plan
  catalog, queue, worker, providers); only the database and — with quota
  enforcement on — an empty plan catalog can fail it. Alongside it, the worker
  gained a heartbeat and a compose healthcheck, so a `while True` that stops
  looping is visible instead of silent.

  What that leaves for A8 proper is the *pages*: the jobs/queues board with
  retry and cancel, AI-provider status with spend rollups (now possible —
  session 25's credit ledger is the first per-org spend data the platform has),
  usage analytics, and error-tracking wiring. The health data this session
  exposes is the input to the health page, not the page.

  Residual: a wedged worker is detected and **not restarted** (tech-debt #81 —
  Compose does not restart unhealthy containers), and `/healthz` re-queries on
  every request (#82).

### P7.9 — Hardening + docs (stage A9, exit gate)
- **Goal:** cross-tenant leakage suite (the merge gate for everything after),
  audit completeness review, ADRs, operator runbook, docs sync.
- **Dependencies:** all of Phase 7. · **Complexity:** M · **Status:** **partial**
  — the **audit completeness review is done** (2026-08-09, session 26, ADR-48),
  pulled forward out of order because tech-debt #71 had been open for two
  sessions and its sharpest case was a security event that recorded nothing:
  refresh-token reuse detection revokes an entire sign-in family for suspected
  theft, and wrote no row. Six mutating paths now emit, plus `billing:quota_denied`
  for refusals, which ADR-45 made the likeliest thing to happen to a live user.

  The review also **changed the standard the exit gate is measured against**.
  "Every mutating action emits an audit event" is not a rule this system can
  keep — a successful refresh rotation is a mutation, fires four times an hour
  per device, and auditing it would bury the trail. The gate is now **every
  mutation with a consequence emits, and every deliberate silence has a test
  asserting the silence**; `tests/test_audit_coverage.py` is where both halves
  are proven.

  **The cross-tenant leakage suite is also done** (2026-08-09, session 26,
  fourth loop) — `backend/tests/test_cross_tenant_leakage.py`, 34 tests, the
  named M1 exit criterion. Built as a **census rather than a checklist**: every
  operation is read out of the live OpenAPI schema and matched against an
  explicit tenancy classification, so **an unclassified route fails the suite**
  and the file cannot go stale as the surface grows. Every probe is a pair — the
  owner must succeed *and* the stranger must get 404 — because a probe that only
  checks the 404 passes just as happily against a route that is dark behind a
  feature flag. It substantially repays tech-debt #63 and found #89 on the way
  in (the quota kill switch does not cover the backlink refresh path).

  It shipped **ahead of its stated dependency on `platform-back-office`**. That
  dependency assumed A7 would land first; A7 is blocked on operator item B16,
  and holding the milestone's central safety claim behind an operator decision
  would have left "zero cross-tenant reads" unchecked indefinitely. When A7
  lands, its routes will fail the census until they are classified — which is
  the mechanism working as designed rather than a gap.

  **CSV export on the audit log** (admin-panel-plan §6) shipped in the same
  session's fifth loop: same filters as the list, a per-row integrity verdict,
  a 5000-row ceiling, and an `audit:export` event recording who took a copy and
  what they filtered to — never the contents.

  **What A9 still owes:** the operator runbook, and the `audit-emit-no-outbox`
  hardening — a deliberate trade rather than a defect (an audit write failure
  must never 500 a request). Neither is a code-correctness gate.

### P7.10 — Analysis history per organization
- **Goal:** let a customer find the analyses their organization has run.
- **Why now:** P7.6 gave `analyses` an `org_id` and nothing read it. The only
  route back to a result was the URL the submitter was redirected to, so closing
  the tab lost the run — the data claimed an owner and the product gave that
  owner no way in (tech-debt #77). It is also the first screen that makes
  session 25's metering visible to the person paying for it, which matters
  directly after a change that put every organization on Free.
- **Dependencies:** P7.6 (the `org_id` it reads). · **Complexity:** M ·
  **Status: DONE** (2026-08-09, session 26, ADR-49).
- **Deliverables:** `GET /api/v1/analyses` (`analysis:read`, org-scoped, paged,
  status filter); `AnalysisSummaryOut`/`AnalysisListOut`; `services.analyses.
  list_org_analyses`; the `/analyses` screen; a nav entry under AI Visibility;
  14 backend and 13 frontend tests.
- **Acceptance:** another tenant's runs are absent, an org-less context raises
  rather than listing everything, pre-P7.6 and checker runs appear in nobody's
  history, paging never repeats or skips a row, and an unmeasured run reports a
  **null** score that the UI draws as an em dash.
- **Two notes for whoever builds the next list route.** The route is
  authenticated while its sibling `GET /analyses/{id}` is not, and that is the
  design rather than an oversight: an unguessable id can be a capability, an
  enumeration never can (ADR-49). And it is the **first application call site of
  `tenancy.scoped()`** — the fail-closed seam three documents described as
  shipped with zero callers. That does not close tech-debt #63; the A9 leakage
  suite does. It does mean the seam now has a worked example to copy.

---

## Phase 8 — Backlink Intelligence (roadmap M2)

*Spec: [backlink-intelligence-plan.md](backlink-intelligence-plan.md)
(scope authority) · stages B1–B8 → cards P8.1–P8.8, decomposed at build
time. Gated on Phase 7's quota/credit foundation (P7.6) and the operator's
vendor + budget decision (**A4**). Engine done and now reachable over HTTP
(P8.1/P8.3-API/P8.4-delta/P8.5/P8.6/P8.7), and **the screens shipped
2026-08-06** (P8.3 complete). What M2 still lacks is a licensed index, not
code: `BACKLINKS_ENABLED` stays off in production, so every route answers 404
to a customer until P8.2's vendor adapter lands behind operator gate A4.*

- **P8.1 — `BacklinkSource` seam + mock + schema v1** (S/M): protocol,
  deterministic mock, `backlink_profiles`/`backlinks`/`link_events`; $0
  DRY_RUN end-to-end. **Status: DONE** (2026-08-05, session 21, ADR-36) —
  shipped as five tables (`backlink_imports`, `backlinks`, `link_events`,
  `referring_domain_rollups`, `backlink_competitors`), a cost-raising pinned
  price table, and a mock that is a pure function of `(domain, cycle)` so
  multi-refresh behaviour is testable without a clock.
- **P8.2 — First licensed adapter + metered import** (M): vendor per A4;
  cost tagging into the credit ledger; quota-gated initial import. Status:
  todo (blocked: A4).
- **P8.3 — Inventory UI: links / referring domains / anchors** (M):
  filtering, sorting, CSV/XLSX export. **Status: DONE** (2026-08-06, session
  23) — screens shipped on top of the API half. `/backlinks` picks a project
  (deliberately no second create-project flow — two front doors to one entity
  is how a domain ends up with a split profile) and `/backlinks/[projectId]`
  carries five tabs: Overview (authority decomposed into its published terms
  plus its caveats, velocity, anchors, toxicity bands), Backlinks
  (server-side filter/sort/page), Referring domains (every band rendered with
  its reasons, never behind a click), New & lost, and Opportunities (gap +
  unlinked mentions, each labelled with where it came from). The nav entry
  graduates from `soon` to `live`.
  Three things the UI is responsible for that the API cannot enforce: a
  **null score renders as an em dash**, never a confident `0`; an
  **unmeasurable pull is labelled as such** wherever its numbers appear, so a
  flat chart is not read as stability; and the **switched-off state is
  first-class**, since `BACKLINKS_ENABLED=0` is what production actually
  serves — the page tells the customer no index is connected rather than
  showing an error. Off is told apart from missing by asking whether the SEO
  project itself loads, not by matching on the 404's prose.
  Exports are authorized fetches rather than links: the access token is
  bearer-only and held in memory, so an `<a href>` would 401 as a page
  navigation. **Residual:** XLSX (CSV ships), and competitor management still
  has no screen — the API has it. Frontend suite 281 → **305**.
  The earlier partial status, for the record — the **API half**: **twelve**
  route handlers under
  `/api/v1/seo-projects/{id}/backlinks` (summary, inventory,
  referring-domains, anchors, events, opportunities, competitors CRUD = 3,
  refresh, CSV + disavow export), registered in `app/api/main.py` and dark
  behind `BACKLINKS_ENABLED` as a router-level 404 rather than a 403.
  `app/services/backlinks.py` is the seam: it owns the one subject-key
  normalization both reads and writes use, advances the mock's cycle from the
  count of prior imports, and rescores authority/toxicity after each import
  because `run_import` deliberately stops at the rollups. Reading is
  `backlink:view`, refreshing is `backlink:refresh` (it spends), exporting is
  `export:data`; quota refusal is 429 and credit refusal 402, so a UI can tell
  them apart. CSV is capped at the list ceiling — a full-profile dump belongs
  in an export artifact (plan §4), not a synchronous request.
- **P8.4 — Monitoring: scheduled refresh, new/lost deltas, liveness
  verification** (M/L). **Status: PARTIAL** (2026-08-05, session 21) — the
  delta engine is done and is the milestone's load-bearing piece:
  measurability gating, vendor-`first_seen` birth classification, canonical
  identity keys, two-miss `lost`, `regained`. **Not done:** the liveness
  verifier (`LinkVerifier` seam is specified, unimplemented) and scheduled
  refresh — both need the worker/queue wiring, which is the next slice.
- **P8.5 — Metrics: transparent Yanki Authority, velocity, history** (M):
  formula published on the methodology page. **Status: DONE in code**
  (2026-08-05, session 21) — four weighted terms that sum to the score shown,
  each self-explaining, caveats in the payload; velocity reads the import
  snapshots so it survives pruning and vendor churn. **Residual:** the
  methodology *page* still needs the section (tech-debt).
- **P8.6 — Toxicity assessment + disavow export** (M): advisory wording;
  reasons always shown. **Status: DONE** (2026-08-05, session 21) — domain-grain
  scoring from vendor spam signal, near-zero authority, suspicious TLD, /24
  clustering and money-anchor density; a band without reasons fails a test;
  Google-format disavow carrying its evidence as comments. Nothing auto-disavows.
- **P8.7 — Competitor profiles, gap analysis, outreach lists** (M/L): incl.
  unlinked-mention source from existing footprint/citation data. **Status:
  DONE in code** (2026-08-05, session 21) — gap ranks by competitors ×
  authority; `unlinked_mentions` reads `geo_records.citations` and
  `serp_checks` for pages that named the brand and never linked, at **zero
  vendor cost** (D10). **Residual:** competitor profiles are fetched by the
  same importer but nothing schedules them yet (shares P8.4's residual).
- **P8.8 — Alerts, report blocks, cost-soak, docs** (M): exit gate per the
  plan doc's acceptance list. Status: todo.

---

## Phases 9+ — reserved (roadmap M3–M9)

*Reserved to keep IDs stable: Phase 9 = M3 (Technical SEO & Site Audit
productization), Phase 10 = M4 (AI Visibility & GEO Monitoring), Phase 11 =
M5 (Entity & Local), Phase 12 = M6 (Competitive & Reporting), Phase 13 = M7
(Automation & Agents), Phase 14 = M8 (Enterprise), Phase 15 = M9 (Advanced
AI). Each is decomposed into cards only when its milestone starts — the
product-level scope lives in [roadmap.md](roadmap.md) and
[feature-parity.md](feature-parity.md) until then.*

---

## Technical debt & assumptions (living list)

Keep this honest — see [design.md](design.md) ADR log for the "why" behind
decisions.

- ~~Deploy/rollback scripts are UNTESTED~~ **repaid 2026-07-10 (P4.2):** both
  exercised on the real server (rollback's pruned-image rebuild branch is the
  only path still unproven — tech-debt #17).
- **Gemini + Perplexity are stubs** (planned — roadmap 2b), not a shortcut to hide.
- **Prompt generation is templated, not LLM** (deliberate — testable + free;
  roadmap 2d LLM prompt engine supersedes).
- **`llm_cache` is within-job only** for the MVP; the cross-account cache (the real
  cost lever) is roadmap 2d.
- **Real-key cost is unvalidated** until P4.1 — the biggest open risk to the
  pricing story.
- **Assumption:** SQLite covers unit tests and Postgres covers queue/jsonb
  tests; if a model needs a Postgres-only type in a hot path, revisit P1.2.
</content>
