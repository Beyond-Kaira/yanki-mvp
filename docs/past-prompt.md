# Past Prompts

Archive of prompts already executed by AI-assisted development sessions.
Newest entry last. The active brief lives in `resume-prompt.md`.

---

## Session 1 — 2026-07-09

**Prompt executed:** "using workflows implement and follow @docs/resume-prompt.md"
(the founder-orchestrator brief, applied to the then-empty repo).

**Outcome:** Phases 0–3 delivered and verified in one orchestrated pass — see
[sessions/2026-07-09-01.md](sessions/2026-07-09-01.md). The next-session brief
lives at the end of that session log (§6).

---

## Session 2 — 2026-07-09

**Prompt executed:** "Using workflows, continue implementation. Is anything
expected from me? If so, log here and also to an operator expected md file.
Start from @docs/resume-prompt.md" — resolved via the session-1 brief
(sessions/2026-07-09-01.md §6): P4.1 was operator-blocked (no keys), so the
key-free alternates P4.3 + P4.5 ran, plus P4.4 authoring.

**Outcome:** P4.3 done (gitleaks in CI + pre-commit, red/green proven locally),
P4.4 authored (e2e CI job, unproven until first push), P4.5 done (9-finding
audit, 8 fixed, axe test layer added). See
[sessions/2026-07-09-02.md](sessions/2026-07-09-02.md); the next-session brief
lives at the end of that log (§6).

---

## Session 3 — 2026-07-09 → 07-10

**Prompt executed:** "Using workflows, continue implementation. Is anything
expected from me? If so, log here and also to a operator expected md file.
Start from @docs/resume-prompt.md" — resolved via the session-2 brief
(sessions/2026-07-09-02.md §6): both operator gates still closed (no
`deploy/.env` keys, no GitHub remote), so the neither-gate branch ran:
**P4.6** — decompose roadmap "Next" 2a into a Phase-5 task breakdown
(planning only).

**Outcome:** P4.6 done — Phase 5 (P5.1–P5.11, the free public checker) added to
implementation-plan.md with its build gate, lanes, and merge risks; no code
changed. See [sessions/2026-07-10-01.md](sessions/2026-07-10-01.md); the
next-session brief lives at the end of that log (§6).

---

## Session 4 — 2026-07-10

**Prompt executed:** "Using workflows, continue implementation. Is anything
expected from me? If so, log here and also to a operator expected md file.
Start from @docs/resume-prompt.md" — resolved via the session-3 brief
(sessions/2026-07-10-01.md §6) **as superseded by its §9 post-close
addendum**: the operator had pushed to GitHub and the first CI run was 4/5
green with e2e red, so the push-branch ran: fix the e2e job, prove all five
CI jobs green.

**Outcome:** e2e fixed (install-order: npm ci + Playwright before the
bind-mounting compose boot — dockerd was root-owning the anonymous-volume
mountpoint), verified locally by repro before pushing; run 29059944092 =
5/5 green with the Playwright spec's first-ever execution (`1 passed`,
6.6s) → P4.4 done; action majors bumped off Node 20 (checkout v7 /
setup-node v6 / setup-uv v7), run 29060093072 = 5/5 green, deprecation
annotations cleared. Tech-debt 2–3 repaid (list renumbered). See
[sessions/2026-07-10-02.md](sessions/2026-07-10-02.md); the next-session
brief lives at the end of that log (§6).

---

## Session 5 — 2026-07-10

**Prompt executed:** "Using workflows, continue implementation. Is anything
expected from me? IF so, log here and also to a operater expected md file.
Start from @docs/resume-prompt.md" — resolved via the session-4 brief
(sessions/2026-07-10-02.md §6): `deploy/.env` still had empty keys, so the
no-keys branch ran — the last key-free task, hygiene debt #10 (`next lint`
→ ESLint CLI).

**Outcome:** lint script migrated to `eslint . --ext .js,.jsx,.ts,.tsx
--max-warnings 0` with `next-env.d.ts` ignored (2-line diff, `fa13839`;
ESLint 8 + eslintrc deliberately kept, flat config + ESLint 9 deferred to
the Next 16 bump as new debt #16); verified by an exact local mirror of the
CI frontend job + adversarial review, then CI run 29062634057 = 5/5 green.
Old debt #10 repaid (hygiene tail renumbered). **No key-free work remains**
— everything now waits on the operator (keys → P4.1, then P4.2). See
[sessions/2026-07-10-03.md](sessions/2026-07-10-03.md); the next-session
brief lives at the end of that log (§6).

---

## Session 6 — 2026-07-10

**Prompts executed:** "which part of the roadmap is remained for the mvp? …
we will be serving the product from this vps on yanki.beyondkaira.com dns is
set. Put this also to the roadmap." (deploy retarget — landed as session-5
post-close addendum), then "Use the cheapist models from antropic and openai
x2", then "Just added the api keys" → per the standing brief, keys present ⇒
**P4.1**.

**Outcome:** OpenAI provider switched to `gpt-5-nano` ($0.05/$0.40; Anthropic
already on Haiku 4.5, the cheapest); **first live run completed** — real KYC +
`geo_score=0.2` for anthropic.com in ~40s, measured **$0.0132/analysis**
(Anthropic leg) ≈ 1% of the $49 plan (NFR-1 bar: <35%). Discovered the
operator's OpenAI key has `insufficient_quota` (new operator item 1b); the
OpenAI cost leg records after billing is fixed. P4.1 done → MVP 31/32 ≈ 97%,
readiness ~85%; only P4.2 (supervised deploy) remains. See
[sessions/2026-07-10-04.md](sessions/2026-07-10-04.md); the session-7 brief
lives at the end of that log (§6).

---

## Session 7 (2026-07-10, #05) — brief executed: the P4.2 branch

The session-7 brief (end of
[sessions/2026-07-10-04.md](sessions/2026-07-10-04.md) §6) offered two
branches: OpenAI re-run if quota existed (it didn't — still
`insufficient_quota`) and **P4.2 supervised deploy if the operator was
present** — the operator opened with "Let's deploy website. Using
workflows", so the deploy branch ran and completed: P4.2 done,
https://yanki.beyondkaira.com live, MVP 32/32. See
[sessions/2026-07-10-05.md](sessions/2026-07-10-05.md); the session-8 brief
(start Phase 5 / P5.1) lives at the end of that log (§6).

## Session 8 (2026-07-10, #06) — operator-directed: go live + KYC card

No archived brief ran verbatim: the operator opened with direct directives
("run mode: live-providers; KYC is very important — show it on the result
page; OpenAI is accessible now; Caddyfile pushed"), which superseded the
session-8 brief's P5.1 default. Delivered: KYC profile card
(implement+verify workflow, d75c852), prod flipped to DRY_RUN=0, first full
live panel on prod ($0.0162/analysis measured — P4.1 residual closed), and
P5.0 (rate-limit slice) added to the plan as the new first Phase-5 task.
See [sessions/2026-07-10-06.md](sessions/2026-07-10-06.md); the session-9
brief (P5.0 → P5.1) lives at the end of that log (§6).

## Session 9 (2026-07-10, #07) — P5.0 + P5.1 via workflows

Ran the session-8 brief (archived above in the session-8 §6 pointer) as
written: P5.0 (rate limit on the live endpoint, 31061c0) then P5.1 (checker
submit + leads + 24h reuse, a8f0a06), both implement→adversarial-verify
workflows, both deployed and live-verified (429 with Retry-After on prod;
cache-hit + lead smoke at $0). Verifier catches: a latent 500 on limit=0
(hardened into a kill-switch) and a critical worker-poisoning bug (worker
would fail checker:// rows — guarded until P5.2). See
[sessions/2026-07-10-07.md](sessions/2026-07-10-07.md); the session-10
brief (P5.2 → P5.3) lives at the end of that log (§6).

## Session 10 (2026-07-10, #08) — operator bug report: KYC wrong on SPA sites

No archived brief ran: the operator reported live KYC failures ("KYC could
not get the correct things from the company website… prompts too generic…
solve this problem first"), preempting P5.2. Two workflow rounds (c8a1932,
e120f56): SPA JS-bundle text mining in discovery, anti-hallucination KYC
prompt + ccTLD location fallback, category-first prompt templates with
brand probes. Live-verified on prod (score 0.0→0.1, KYC correct). See
[sessions/2026-07-10-08.md](sessions/2026-07-10-08.md); the next brief is
session 9's §6 (P5.2 → P5.3) with that log's §6 amendments.

## Session 11 (2026-07-10, #09) — operator confirmations + full LLM answers

Operator ticked items 0–2 ($10 console caps set; KYC fix verified; card
approved pending brandkit), asked how KYC is generated (answered: live
fetch + live LLM extraction, nothing hardcoded outside DRY_RUN), and asked
for on-demand full LLM responses — shipped via workflow (3106cae):
expandable per-row full answers in ResultsTable, axe-tested both states,
deployed. See [sessions/2026-07-10-09.md](sessions/2026-07-10-09.md);
the next brief remains session 9's §6 (P5.2 → P5.3) with the session
10/11 amendments.

## Session 12 (2026-07-10, #10) — P5.2 + P5.3 + P5.6, checker backend complete

Operator said "continue implementation using workflows" (+ mid-session:
close when workflows done; docs-only changes never via workflow). Three
implement→3-lens-adversarial-verify workflows landed P5.2 (d6e7253, checker
pipeline branch, debt #6/#19 repaid), P5.3 (c5e4f6d, presence map +
competitors; verify caught possessive-exclusion bug pre-merge), P5.6
(7542751, kill-switch + limits + cost cap, debt #21 repaid). Deployed dark
(CHECKER_ENABLED=0, live-verified 503 + zero rows, $0 spend); co-tenants
untouched; CI 5/5. See [sessions/2026-07-10-10.md](sessions/2026-07-10-10.md)
§6 for the next brief (P5.4 → P5.5, or P5.7 if keys arrive).

## Session 13 — 2026-07-10 (#11 today)

**Prompt executed:** "Using workflows, continue implementation… Start from
@docs/resume-prompt.md I have added all api keys. This is the last session and
dedicated to frontend refactor according to brandkit right?" — i.e. the
session-12 §9 superseding next-session prompt (P5.12 headline + P5.7 on keys
+ P5.4/P5.5), executed in full and exceeded. Mid-session operator additions:
the waitlist + Resend email notifications (became P5.13); an operator-file
rewrite into answer-sheet form; three status reports. Full log:
`sessions/2026-07-10-11.md`.

## Session 14 — 2026-07-28 (#02 today)

**Prompt executed:** "implement by mini-commits. but dont push them i will do
it tomorrow after review." No scope named, so it was taken from the previous
commit on the branch (`f5b5eb4`), which proposed six ordered discovery/KYC
steps and split them into "clear to build" (1, 2a, 3, 4, 5) and "needs operator
sign-off" (2b, 6). The clear five were implemented, one commit each, plus five
docs commits; **nothing pushed, nothing deployed**. The two parked steps became
operator question **A2**. Full log:
[sessions/2026-07-28-02.md](sessions/2026-07-28-02.md) — §8 is the next brief.

---

## Session 20 — 2026-08-05

**Prompt executed:** the operator's re-planning brief — "Analyze Yanki,
create a roadmap, and update planning documents": read
`docs/Yanki_Geo_Intelligence_Report.pdf` completely, analyze the whole
repository, build a competitive feature-parity analysis and differentiation
proposal, plan the Admin Panel (highest priority) and Backlink Intelligence
(second), produce a milestone roadmap, and update every planning/handoff
document — **implementing nothing**.

**Note on the previous brief:** session 19's next-session prompt
(sessions/2026-08-03-04.md §10 — push PR #13 and PR #4, don't merge without
an answer on tech-debt #52) was **overtaken by events before any session ran
it**: PRs #4, #13, #23 and #11 were pushed and merged by the team on
2026-08-03/04 outside the session process. Its durable items were carried
into the new plan instead (#49/#50/#52 → Phase 7; the merge-hygiene rule →
resume-prompt.md First Task).

**Outcome:** the platform roadmap adopted (ADR-33): roadmap.md rewritten as
milestones M1–M9; new planning set (feature-parity.md, differentiators.md,
admin-panel-plan.md, backlink-intelligence-plan.md, architecture-target.md);
implementation-plan gained Phase 7 (Admin Platform, current priority) and
Phase 8 (Backlink Intelligence); resume-prompt.md updated to the platform
mission; tech-debt #54/#55 recorded for the undocumented merges; operator
items A3/A4/B7 raised. Docs only — no code changed. Full log:
[sessions/2026-08-05-01.md](sessions/2026-08-05-01.md) — §8 is the next
brief.
