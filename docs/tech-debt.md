# Technical Debt — living list

*Per [session-rules.md](session-rules.md): shortcuts are fine, hidden shortcuts
are not. Every session appends here and removes what it repays. Ordered
roughly by risk.*

Last updated: 2026-08-09 (**session 26** — the audit-coverage session).

**Session 26 changes to this list, up front:** **#71 REPAID** — the six mutating
paths that emitted nothing now emit, including refresh-token **reuse
detection**, which revoked an entire sign-in family for suspected theft and
wrote no record of it (ADR-48). Two things about the repair are worth reading
before the new items. First, the rule it settled on is *not* "audit every
mutation": a successful token rotation is a mutation and is deliberately silent,
because it fires four times an hour per device and would bury the trail — so the
rule is **every mutation with a consequence emits, and every silence has a test
asserting it**. Second, `audit_events` is append-only by database trigger, which
means anything written there is permanent; the two paths carrying an email
address store the *reference* and drop the *value*, so the erasure path this
milestone still owes cannot end up in conflict with the integrity guarantee.
**Three new items, #84–#86**, and the one to read is **#84**: recording refusals
means a client retry-looping into a 429 writes a row per retry.

**#77 REPAID** in the same session (ADR-49) — the analyses a customer runs are
now listable at `/analyses`, which is the first screen that makes P7.6's
attribution visible to the person paying for it. It is also the **first
application call site of `tenancy.scoped()`**, the fail-closed seam that three
documents described as shipped and that had none (**#63 — still open**: one
call site is not a guarantee, and the A9 leakage suite is what closes it).
**Two new items, #87–#88**, and the one that matters is **#87**: the query has
no supporting index, because an index is a migration and migrations are gated
on operator item B13 — so it must ride along with the next migration rather
than be discovered under load.

**Both PRs merged and deployed at session close** — production moved from
`ddf3167` to **`e470244`**, so everything in this header is live rather than
pending. New: **#92** (the documented plan-tier escape hatch is not in the api
image, found by running the documented command on the box). Also worth knowing
for the next stacked pair: merging the parent with `--delete-branch` **closed**
the child PR instead of retargeting it.

**#63 SUBSTANTIALLY REPAID, deliberately not closed** — the fourth loop built
the **M1 exit gate**: `tests/test_cross_tenant_leakage.py`, 34 tests, written to
#63's own instruction rather than as a spot-check. Every operation is read out
of the live OpenAPI schema and must carry a stated tenancy classification, so
**an unclassified route fails the suite**; every probe is a pair (the owner
succeeds *and* the stranger gets 404) so it cannot pass vacuously. It stays open
because "no route leaks" is not "no query can" — see **#90**. **Two new items,
#89–#90**, and #89 is the kind of finding this suite exists to produce: an
owner-side probe returned **429 with quota enforcement switched off**, which
revealed that the kill switch does not cover the backlink refresh path even
though its docstring said it could not fail that way.

This session also fixed two CI gates that session 25 could not see from a
laptop and that its own log recorded as green: the scoped **formatting gate**
(seven of its files were unformatted) and the **SERP stack check**, which
submits an analysis through real compose and had been 401ing since ADR-45 closed
that route to anonymous callers. Neither was a code defect; both were the branch
being unverifiable until it was pushed. Measured suite at session 26 close:
**952 backend passed / 7 skipped** with Postgres, **327 frontend across 57
files**, `make test` exit 0.

Earlier — 2026-08-09 (**session 25** — the quota-enforcement session).

**Session 25 changes to this list, up front:** the session ran two loops and
this header covers both. **Loop 2 built the engineering half of operator item
B13** (database backups, ADR-46) — `deploy/backup.sh`, `deploy/restore-check.sh`
and a pre-migration snapshot in `deploy.sh`, rehearsed end to end against live
production. Its residuals are **#78–#80**, and the one to read is **#79**:
backups live on the same box as the database, which covers a bad migration and
not a lost VPS.

**Loop 3 closed the last two P0 rows** (`deep-health-endpoint` and
`worker-liveness-healthcheck`, ADR-47): `/healthz` was a hardcoded literal that
the deploy gate greps, and a `while True` worker that stopped looping was
invisible. Residuals **#81–#83**, and the one to read is **#81**: a wedged
worker is now *detected* and still not *restarted*, because Compose does not
restart unhealthy containers.

**Loop 1 (quota enforcement):** **#63 PARTIALLY REPAID** —
`readable_analysis()` now has a call site. `GET /api/v1/analyses/{id}` routes
through it, which is the first time the NULL-is-public rule is applied by the
function that owns it rather than by nothing at all. `scoped()` still has zero
call sites and the underlying complaint stands: isolation is per-route
discipline, and the A9 leakage suite is still what would catch a route that
forgets. **Five new items, #73–#77.** The two worth reading are **#74** (plan
credit is never granted, so `reserve()`'s credit gate would refuse every request
and is structurally unusable — this is why enforcement meters counts and merely
*records* money) and **#75** (two concurrent submits from one org can both pass
a quota check; worst case is one extra unit, and the fix waits until a metered
unit is expensive). Also **#73** (there is no anonymous analysis surface any
more — a product decision now living in a route signature), **#76** (nothing
asserts the plan catalog exists before a customer needs it) and **#77** (runs
are attributed to an org and there is still no screen that lists them).
Measured suite at session 25 close: **933 backend passed / 7 skipped** with
Postgres, **327 frontend across 57 files**, `make test` exit 0. *(Measured at
this session's start, before any of its work: **897 backend passed / 7
skipped**, **319 frontend across 56 files**.)* The backup tooling is shell and
carries no unit tests; it was verified by running it against the live database
and by exercising both failure paths (ADR-46, session log §9).

Earlier — 2026-08-08 (**session 24** — the deploy-safety and P7.5 session).

**Session 24 changes to this list, up front:** **#17 MOSTLY REPAID** (the
rollback pruned-image branch no longer resurrects the fused migrate-on-boot
compose, and no longer leaves detached HEAD — ADR-42; residual is that it is
still unproven against a live rollback). **Ten new items, #63–#72.** The one to
read first is **#63**: `tenancy.scoped()` and `readable_analysis()` — the
fail-closed tenancy seam that ADR-35, `architecture-target.md` and the P7.1 card
all described as shipped — **have zero call sites**. Isolation is real but it is
per-route discipline, so a route that forgets to filter compiles and leaks. All
three documents are corrected; the guardrail itself is A9 work. Also new:
**#64** (three Site Audits stranded `queued` in production, needing operator
cleanup), **#65** (the site-audit worker would hold every secret — its
documented isolation was never built), **#66** (feature flags are discovered by
catching a 404), **#67–#69** (P7.5 residuals: no device fingerprint without a
migration, no live 403→clear-active-org, an `/auth/me` N+1), **#70** (the
rollback guard's hardcoded boundary SHA), **#71** (mutating paths still emitting
no audit event — including refresh-token **reuse detection**, which revokes a
whole family and records nothing), and **#72** (session 23 shipped without any
of its eight close deliverables; the log is reconstructed, the reasoning is
gone). Measured suite at session 24 close: **897 backend passed / 7 skipped**
with Postgres, **319 frontend across 56 files**, `make test` exit 0.
*(The counts recorded below for session 22 — 835/281 — were correct then;
session 23 added tests without updating them. Measured at this session's start,
before any of its work: **873 backend passed / 7 skipped**, **305 frontend
across 54 files**.)*

Earlier — 2026-08-05 (**session 22** — the Admin Panel session).

**Session 22 changes to this list, up front:** **#52 REPAID** (an account now
grants something — the Admin Panel is a real signed-in destination that invites,
assigns roles and shows the audit trail). **#57 PARTIALLY REPAID** (a formatting
gate exists, scoped to changed files; the repo-wide sweep is what remains).
**Four new items — #59** (`audit.emit` swallows its own errors, so the trail is
tamper-evident but not loss-evident), **#60** (workspace-scoped roles are
honoured at org grain; `workspace_grants` was never built), **#61** (the
organization profile is read-only — no PATCH), **#62** (the frontend has no
Prettier config, so `make fmt` would rewrite it into a style nobody chose).
**#54's documentation half is sharpened, not repaid** — see the item for the
exact sections of `architecture.md` still describing the retired four-engine
pipeline. Measured suite at session 22 close: **835 backend passed / 7 skipped**
with Postgres (820/22 hermetic), **281 frontend across 51 files**.

Earlier — 2026-08-05 (session 21, the first Phase 7 build session.
**One latent production hazard found and repaid in the same pass, before it
fired:** `alembic check` failed on a clean, fully-migrated database — eight
indexes existed only in migrations and never in `Base.metadata`, which
autogenerate reads as eight indexes the models want *dropped*. The next
routine `alembic revision --autogenerate` — exactly what P7.1 needs — would
have proposed `DROP INDEX` against production, including the site-audit queue
index and the checker-reuse index. Nothing caught it because every test builds
its schema with `create_all`, so the models were the only definition under
test. Repaid in `aa0c80c`: the eight are now declared on the models (no
migration change, no production DDL — they already exist there), and a new
`backend/tests/test_migrations.py` keeps it that way with an upgrade/check/
downgrade round trip against real Postgres. Two new items — **#56** (PRs #24 and #25 merged the same day, again outside the
session process, adding ~5,800 lines of frontend — a Semrush-style app shell
whose navigation is a product information architecture the roadmap never
agreed to — with no ADR, plan card or session log; and its Site Audit UI
makes #55's unhardened backend user-reachable). One item **closed by
evidence, not by code**: the operator-facing half of **#54** — prod
`deploy/.env` carries both `OPEN_ROUTER_KEY` and `TAVILY_API_KEY`, and the
eight most recent live analyses all completed, so the `GEO_MODE=measured`
key requirement is satisfied in production (operator item **B7** ticked);
#54's documentation half stays open. Also corrected here: the recorded test
counts everywhere were stale — the suite is **488 backend + 205 frontend**,
not 170/65. Earlier — session 20, the re-planning session — docs only,
no code changed: two new items — **#54** (PR #11's measured/simulated GEO
pivot merged with zero documentation: no ADR, no session log, no plan card;
architecture.md/README pipeline descriptions and recorded test counts are
stale against it; `geo_mode=measured` makes OpenRouter + Tavily keys
**required** when `DRY_RUN=0` — see operator-expected **B7**, possibly
production-affecting) and **#55** (PR #23's Site Audit backend merged with
only `site-audit-integration.md`: no ADR, no plan card, its production-
hardening list unresolved, its worker absent from the prod compose, and no
UI reaches it). No repayments this pass — but #49, #50 and #52 now have
scheduled homes in Phase 7 (P7.5, P7.6, P7.4 respectively). Earlier —
2026-08-03 (account screens, PR #13 review response, merged
against main after items #27-48 landed there: five new items — **#49**
(password reset has no endpoint, so it ships no screen), **#50**
(no terms text, so sign-up asks for no agreement), **#51** (every cold load POSTs
`/auth/refresh`, anonymous visitors included), **#52** (an account grants
nothing — no route is protected and there is no signed-in destination), **#53**
(the cross-tab refresh guard degrades on browsers without Web Locks). No
repayments this pass. Earlier the same day — SEO audit, ADR-31: four new
items — **#45** (the
audit sees at most six pages but its findings read as site-wide), **#46**
(the severity weights are editorial and uncalibrated), **#47** (one extra
HTML parse per page), **#48** (no llms.txt check)). Earlier the same day —
(migrate-before-serve, ADR-30 / GitHub issue #16:
docs-only follow-through, no new numbered items. **#16 repaid in prod** — the
migration now runs as a one-shot driver step that finishes before any app
container starts, so the worker's first-boot `UndefinedTable` race is gone in
prod — but **kept open for dev**, whose compose still fuses `alembic upgrade
head` into the api's boot command. **#17** gains a new wrinkle: rollback's
pruned-image `git checkout` would resurrect that fused command and re-break the
rollback path ADR-30 just fixed. No full repayments this pass. Earlier the same
day — SERP visibility pass, ADR-28: nine new items —
**#34** (SERP score is binary and unweighted, like the GEO score), **#35** (a
SERP is a one-shot snapshot, never re-measured), **#36** (`serp_query_count`=6
is a politeness budget, not a measured one), **#37** (domain matching is
host-suffix, not eTLD+1), **#38** (the measurable/miss split trusts
`unresponsive_engines`), **#39** (query shapes are hardcoded English), **#40**
(integration tests pin one SearXNG tag — the schedule-only `upstream` job is
what catches drift), plus **#41** (own-site matching compares raw host strings,
so an IDN domain can miss) and **#42** (the SERP response is read without a byte
cap) — both raised by an adversarial review of the branch before merge; then
**#43** (DRY_RUN forces the mock SERP source) and **#44** (two of four
engines are refused from this egress IP) when the instance was actually
stood up (ADR-29). No repayments this pass. Earlier — 2026-08-01 (pipeline
quality part two, `pipeline-quality-plan.md`: three new items — **#30**
(`_is_html` byte-sniff closes #28 for known binary formats, not all), **#31**
(SPA bundle extraction still welds punctuation onto real copy), **#32** (the
prompt category filter is a heuristic pending real-profile data), **#33**
(grounding's 1 000-char floor is a guess, not measured). No repayments this
pass. Earlier —
2026-07-28 (discovery + KYC pass: three new items — **#27**
(KYC-stage spend counts toward no cost cap), **#28** (`_is_html` fails open on a
missing Content-Type), **#29** (steps 2b/6 specified but parked on an operator
decision). No repayments this pass. Earlier — 2026-07-10 (session 12 close:
three repayments — #6, #19, #21 —
and one new minor, **#22** (checker cost-cap window/kind-scope not test-pinned).
P5.6: **item 21 REPAID** — `POST /api/v1/checker` now
carries a salted `ip_hash`, a default-OFF `CHECKER_ENABLED` kill-switch, per-IP
and per-brand rate limits, and a rolling-24h daily cost cap, all enforced before
enqueuing and all exempting the $0 24h cache hit; the endpoint is safe to expose
(see ADR-22). Earlier — P5.2: **items 6 and 19 REPAID** — `execute._write_cache`
is now a concurrency-safe `ON CONFLICT DO NOTHING` upsert (Postgres-gated race
test), and `run_pipeline` branches on `kind` so the `claim_next` checker
skip-guard is removed and checker rows run through all six steps with no crawl;
see ADR-20. Earlier — session 9: **item 2 REPAID** — P5.0 landed and is
verified live on prod (5/IP/hour + 100/day rolling caps, 429 + Retry-After
before any row or spend; worst-case abuse now bounded at ≈$1.62/day at the
measured $0.0162/analysis); the item is rewritten below as the narrower
XFF-trust posture note. Three new items from P5.1: #19 (P5.2 must remove the
`claim_next` checker guard), #20 (lead email regex, not RFC validation),
#21 (checker endpoint unthrottled until P5.6 — $0 exposure, row growth only).
Earlier session 8: item 1 largely repaid — the OpenAI leg ran live on prod
(10 × `gpt-5-nano`, measured $0.0026/analysis); what remains of #1 is
KYC-cost persistence + adapter contract tests. Earlier session 7: **old item 1 REPAID by P4.2** — the
deploy + rollback scripts ran for real on the shared VPS (deploy caught and
fixed one real bug: the prod web image build omitted devDependencies). The
list was **renumbered once more**: old 2→1, 3→2, 4→3, 5→4, 6→5, 7→6, 8→7,
9→8, 10→9, 11→10, 12→11, 13→12, 14→13, 15→14, 16→15 (archived logs cite the
numbers of their day; the session-5/6 headers carry the previous maps). Old
#8 (Caddy wiring "never exercised") is REWRITTEN as #7: the wiring is now
proven live — what remains is the manual, non-idempotent publish step and
the two-way pulse-prod lifecycle coupling. Three new items: #16 (worker
boot-race log noise), #17 (rollback's pruned-image branch still unproven +
`git checkout` working-tree hazard), #18 (prod web image ships
devDependencies).)

## Untested / never exercised

1. **Both live adapters are now proven (Anthropic ✅ session 6, OpenAI ✅
   session 8) — two residuals stand.** Session 8 (2026-07-10) ran the full
   live panel ON PROD: 10 × Claude Haiku 4.5 ($0.0135) + 10 × `gpt-5-nano`
   ($0.0026) → **measured full-panel cost $0.0162/analysis** (gemini/
   perplexity stubs $0; real KYC for anthropic.com; geo_score 0.225).
   Remaining: (a) The **KYC call's cost is not persisted** —
   `responses.cost_usd` covers the panel only, so the recorded per-analysis
   cost understates by ~1 call (~$0.002 at Haiku prices with page text as
   input); fold KYC cost into the analysis row if precise invoicing ever
   matters. (b) Still no respx-style contract tests for the adapters; price
   tables remain hardcoded from (now verified) public pricing.

## Accepted MVP shortcuts (by design, revisit before/at launch)

2. **P5.0 rate limiting trusts the first `X-Forwarded-For` entry** (the bulk
   of this item was REPAID in session 9 — the live endpoint now enforces
   5/IP/hour + 100/day rolling caps with 429 + `Retry-After` before any row
   is created). Accepted residue: XFF is client-controllable when a request
   reaches the api without the host nginx edge in front, so the *per-IP* limit
   is spoofable — the *global* daily cap (≈$1.62/day worst case at measured
   cost) is the deliberate backstop, and either limit set to `0` is a clean
   kill-switch (429 everything). Also: the daily-cap `COUNT` has no dedicated
   `created_at` index (fine at MVP volume). Escape hatch unchanged:
   `DRY_RUN=1` + redeploy.
3. **DRY_RUN always analyzes the fixed mock company "Yanki Demo Co"**,
   regardless of the submitted URL (documented in architecture.md). Deliberate:
   keeps the mock deterministic end-to-end.
4. **Mock/KYC prompt coupling:** `providers/mock.py` returns the canned KYC
   profile when the prompt contains the substring `"json object"` — which
   `kyc.build_prompt` includes. Change one, keep the other in sync (both files
   carry comments).
5. **No intra-execute heartbeat.** `claimed_at` is heartbeated between steps,
   not inside the execute loop; an execute step longer than
   `STALE_CLAIM_SECONDS` (300s) could be reclaimed mid-run. Idempotent
   delete-before-rerun makes this safe but wasteful. Fix only if real runs
   approach 300s.
6. ~~**`llm_cache` read-then-insert race** under concurrent workers could raise
   on the unique key.~~ **REPAID (P5.2):** `execute._write_cache` is now an
   upsert — delete any stale row on the key (keeps the refresh-with-fresh-
   timestamp semantic), then `INSERT … ON CONFLICT (cache_key) DO NOTHING` via
   the Postgres/SQLite dialect `insert`, then re-read. A second worker racing
   the same key is a no-op, not an `IntegrityError`; proven by the Postgres-gated
   `tests/pipeline/test_execute_race.py`. Residual (minor): the delete-first step
   means a losing concurrent writer can drop a rival's just-committed fresh row
   and replace it with its own — harmless (both answers valid, timestamp stays
   fresh, response cost is recorded from the generated result, not the cache row).
7. ~~**The Caddy publish step is manual, non-idempotent, and coupled two-way to
   pulse-prod**~~ **LARGELY REPAID by the Caddy → nginx cutover** (see
   `deploy/MIGRATION.md`): the shared containerised Caddy was retired; the edge
   is now a host nginx vhost (`deploy/nginx/yanki.beyondkaira.com.conf`,
   installed under `/etc/nginx`) proxying the loopback binds 8142/8143, and the
   two-way pulse-prod lifecycle coupling is gone (yanki no longer joins
   `pulse-prod_default`; the retired `deploy/caddy/` block was deleted).
   Remaining accepted debt: `make deploy` still does NOT publish edge config —
   the repo's nginx conf and the installed `/etc/nginx` copy must be kept in
   sync manually (`sudo cp` + `nginx -t` + reload, never restart).
8. **The e2e CI job depends on real runner egress to example.com.** DRY_RUN
   mocks only the LLM providers; pipeline step 1 (discovery) genuinely fetches
   the submitted URL, so the spec's `https://example.com` submission needs
   outbound network from the worker container. Accepted: hosted runners allow
   egress and example.com is highly stable; a red e2e *after green health
   waits* is a likely network flake, not an app regression (the job carries a
   comment saying so). Removing the dependency would mean mocking discovery
   under DRY_RUN or whitelisting a stack-served URL past the SSRF guard —
   both app changes made purely for CI; declined for the MVP.

## Hygiene / small

9. **Node 20 on the dev host vs README's recommended 22 LTS** — everything
    green on 20; upgrade opportunistically.
10. **StepProgress / ResultsTable still have no behavior unit tests.** Partially
    repaid: both now carry axe a11y tests
    (`tests/StepProgress.a11y.test.tsx`, `tests/ResultsTable.a11y.test.tsx`), but
    nothing exercises their rendering logic. Add when they grow logic.
11. **gitleaks is pinned in two places that must move in lockstep.** `ci.yml`'s
    `secrets` job (`GITLEAKS_VERSION` + `GITLEAKS_SHA256`) and
    `.pre-commit-config.yaml` (`rev: v8.28.0`). Bump both together — and
    recompute the SHA256 from the release `checksums.txt` — or the CI layer and
    the local hook run different scanner versions.
12. **The pre-commit gitleaks hook is `language: golang`.** pre-commit
    auto-provisions its own Go toolchain to build it, so the first
    `pre-commit run` (or first commit) is heavy and needs network; an offline or
    otherwise constrained first run will stall. No system Go is required, and
    later runs are fast.
13. **Contrast fixes are guarded only by manually computed ratios.** axe's
    `color-contrast` rule is disabled under jsdom (it has no layout or paint —
    see `tests/a11y.ts`), so the P4.5 WCAG ratios are verified by hand, not by a
    running test. A token/color change that regresses contrast would pass CI.
    Re-check the ratios manually when touching the `*-soft` fills or the text
    tokens layered on them.
14. **`npm ci || npm install` fallback can mask lockfile drift.** Used in the
    frontend/contract/e2e CI jobs and both Dockerfiles (originally for the
    no-lockfile bootstrap). With `package-lock.json` now committed, a failing
    `npm ci` silently falls back to `npm install`, which may resolve different
    versions — a green job then doesn't prove the locked tree. Extra edge since
    session 5: a fallback `npm install` could pull a newer in-range
    eslint-config-next whose new warnings would trip the `--max-warnings 0`
    gate in a way the committed lockfile can't reproduce. Drop the fallback
    when convenient (low risk, low priority).
15. **ESLint 8.57 (EOL) + legacy `.eslintrc.json` deliberately kept; flat
    config + ESLint 9 deferred to the Next 16 bump.** Session 5 repaid old
    debt #10 with the minimal-risk diff: only the `lint` script changed
    (`next lint` → `eslint . --ext .js,.jsx,.ts,.tsx --max-warnings 0`), so
    the Next-16-blocking `next lint` call is gone with zero dependency/lockfile
    churn. The deferred half: `--ext` and `.eslintrc.json` BOTH stop working
    under ESLint 9's flat config, so the Next 16 / eslint-config-next 16 bump
    must swap in an `eslint.config.mjs` (FlatCompat pattern, port
    `ignorePatterns` → `ignores`) and drop `--ext` in the same change — plan it
    manually, the official `next-lint-to-eslint-cli` codemod's legacy-config
    conversion is buggy (vercel/next.js#85679). Two accepted quirks meanwhile:
    `--max-warnings 0` is deliberately stricter than `next lint` (warnings now
    fail CI — treat a future warning-level failure as a real gate, not a
    flake), and `postcss.config.mjs` stays unlinted (`.mjs` not in `--ext`;
    `next lint` never covered it either). Note: Next 16 also stops linting
    during `next build`, making this script the ONLY lint gate.
16. **The worker's first-boot `UndefinedTable` race — now repaid in prod, still
    present in dev.** (Tech-debt item #16, *not* GitHub issue #16: that one is
    the rollback bug ADR-30 fixes, and the two numbers collide by coincidence.)
    The original noise: compose started the worker on api `service_started`
    while the api ran `alembic upgrade head` before uvicorn, so the worker's
    first poll could beat the migration and log a full traceback
    (`relation "analyses" does not exist`) before recovering on the next poll
    (observed on the first prod deploy, 2026-07-10; RestartCount stayed 0).
    **Prod (ADR-30): repaid.** The migration is now a one-shot driver step that
    finishes *before* any app container starts, and the prod api command is
    serve-only, so by the time the worker container exists the schema is already
    at head — there is no longer a migration in flight for the first poll to
    race. **Dev (`docker-compose.yml`): unchanged and still racy.** The api
    keeps the fused `sh -c "alembic upgrade head && uvicorn …"` command and the
    worker still `depends_on api: service_started` (which waits for the
    container to *start*, not for the migration to *finish*), so a first-poll
    traceback can still surface locally and in CI's e2e stack. Deliberate: dev
    has no rollback to protect and CI relies on the stack migrating itself. The
    old fix — a db-schema wait or migration-completion gate — now applies to the
    dev half only, if the noise ever confuses anyone.
17. **`rollback.sh`'s pruned-image branch is still unproven and mutates the
    working tree.** P4.2 exercised only the images-present path (same-SHA
    rollback, clean + healthy). If the last-good image was ever pruned,
    rollback does `git checkout <sha>` + rebuild — detached HEAD, fails on a
    dirty tree, and leaves the operator's checkout moved. Surfaced by the
    session-7 pre-flight review; accepted for now (rollbacks are supervised).
    **New wrinkle (ADR-30):** that working-tree mutation is now a *correctness*
    hazard, not just an ergonomic one. `git checkout <sha>` to a last-good SHA
    that predates ADR-30 restores that SHA's `docker-compose.prod.yml` too — the
    one whose api command is the fused `sh -c "alembic upgrade head &&
    uvicorn …"`. So the pruned-image branch rebuilds and `compose up`s the old
    serve-*and*-migrate command, re-introducing exactly the boot-time migration
    ADR-30 removed from the serving path — and it does so in the one scenario
    rollback exists for: a forward deploy that migrated the DB to a new head and
    then failed the health gate. The DB is now past the old image's known
    revisions, so the resurrected fused command's boot `alembic upgrade head`
    exits 255 (`Can't locate revision …`) and crash-loops — the very failure
    ADR-30 proved the serve-only command avoids. The images-present branch is
    safe here: it never checks out, so it `compose up`s the already-built
    last-good image under the *current* serve-only compose file (ADR-30's
    proven-good case); only the `git checkout` branch resurrects the fused form.
    Most acute in the transition window, while `.last-good` still points at a
    pre-ADR-30 release — it fades once last-good is itself post-ADR-30, since
    checking that out restores a serve-only compose. The clean fix keeps the
    compose file out of the checkout: pin it, or roll the image tag back without
    moving the tree at all.

    **MOSTLY REPAID (2026-08-08, session 24, ADR-42).** The crash-loop hazard
    and the detached-HEAD mutation are both closed: the pruned-image branch now
    **refuses** a last-good SHA at or behind `56c1fac` (the migrate-on-boot
    split) with an actionable hand-recovery message rather than resurrecting the
    fused command, and it restores the branch it started on instead of leaving
    the operator's checkout moved. It was repaired *before* Phase 7's A5–A8
    migrations land, which is the window this item warned about. Residual, and
    the reason this is not struck through: the fix was proven in a scratch repo
    with stubbed `docker`/`curl` and a truth table against the real `56c1fac`,
    **not** by a live rollback — the images-present path remains the only one
    ever exercised against production. The boundary constant is its own item
    (**#70**). The originally-suggested clean fix (keep the compose file out of
    the checkout entirely) was not taken: refusing is a smaller, more auditable
    change to code that runs when production is already broken.
18. **The prod web image ships devDependencies.** Session 7's fix for the
    build failure (`npm ci --include=dev`, needed because NODE_ENV=production
    otherwise omits the typescript devDep that `next build` requires) means
    the runtime image also carries dev packages. Correct fix later: a
    multi-stage Dockerfile (build with dev deps, run with `npm ci --omit=dev`
    or Next standalone output). Cost today: image size only.
19. ~~**`claim_next` skips `kind='checker'` rows — a deliberate P5.1 stopgap
    that P5.2 MUST remove.**~~ **REPAID (P5.2):** `run_pipeline` now branches on
    `kind` (a checker row seeds KYC from its brand+category instead of crawling
    its synthetic `checker://` url), so the guard is gone and the worker claims
    checker rows in ordinary FIFO order. `test_claim_next_skips_checker_rows` is
    replaced by `test_claim_next_claims_checker_rows` in
    `backend/tests/test_queue.py`. (Sequence P5.6 — checker rate limit, #21 —
    promptly, since checker rows now actually run and spend on real providers.)
20. **Lead email validation is a minimal regex, not RFC/deliverability
    validation** (`email-validator` isn't installed; the card allowed this).
    Some technically-invalid addresses will be accepted into
    `checker_submissions.email`. Fine for a lead gate; `pydantic[email]` is a
    drop-in swap if lead quality ever matters (relates to operator decision
    on email-gate strength, operator-expected item 13).
19a. **SPA bundle mining prioritizes non-ASCII (localized) literals** to keep
    framework noise out of the 20k text cap — so an **English-only**
    client-rendered SPA whose bundle front-loads runtime strings could still
    have real content truncated away (the live Turkish target works because
    its copy carries Turkish letters). If an English-only SPA misfires the
    same way, add a content-keyword ranking pass. Also: bundle fetches trust
    the `content-length` header + post-hoc truncation, not true streaming —
    a >2MB body without the header downloads fully before truncation.
19b. **Discovery worst-case latency grew**: homepage + 5 links + 3 bundles ×
    15s timeout ≈ 135s theoretical worst case, under but not comfortably
    under `STALE_CLAIM_SECONDS=300` (interacts with debt #5's no-heartbeat-
    inside-a-step). Observed real case: ~0.25s. Revisit if slow sites appear.
21. ~~**`POST /api/v1/checker` has no rate limit until P5.6** (deliberate lane
    ownership — P5.6 adds ip_hash population, limits, kill-switch, cost cap).
    Exposure today is $0 (worker skips checker rows, see #19) and cache hits
    are free, but an abuser can grow the `analyses`/`checker_submissions`
    tables unboundedly.~~ **REPAID (P5.6, see ADR-22):** the checker endpoint now
    derives a salted `ip_hash` (reusing the existing `ip_hash_salt` — no second
    salt) and, for a FRESH run only, enforces in order a `CHECKER_ENABLED` master
    kill-switch (default OFF → friendly parked 503, records nothing), a per-IP
    submissions/hour 429, a per-brand fresh-runs/day 429, and a rolling-24h daily
    USD cost cap (at-capacity 503). A $0 24h cache hit is exempt from all four so
    it still returns its id for the email gate. Fresh-run LLM spend is bounded to
    roughly the daily cap, not eliminated — see the residuals below.
    (The P5.6 card said "tech-debt #3 marked repaid" — a **stale renumbering
    artifact**; the real item is **#21**, repaid here.) Residuals, reported
    honestly: **(a)** the cost cap is **completion-lagged** — it sums
    `responses.cost_usd`, which the worker writes only *after* a run finishes, so
    a just-enqueued run counts as $0 at submit time. Left naked this is a real
    bypass: a distinct-triple, XFF-spoofed burst evades the per-brand and per-IP
    caps and could enqueue an unbounded backlog the worker later spends far past
    the cap. So with real keys the cap also **projects** in-flight fresh runs
    (queued/running `kind='checker'` rows) at a conservative per-run estimate
    (`_EST_CHECKER_RUN_COST_USD`), bounding the concurrent backlog to about
    `cap / est`. Residual overshoot is therefore **bounded to a small multiple of
    the cap** (if true per-run cost drifts above the estimate), not unbounded;
    retune the estimate with the price tables and at P5.7 when Gemini/Perplexity
    stop being $0 stubs. **(b)** the per-IP hash is derived from the first
    `X-Forwarded-For` entry, which is **client-controlled** even behind the
    edge proxy (same caveat as item #2), so the per-IP cap is spoofable; the
    per-brand cap and the projected daily cost cap are the real backstops against
    a spoofed-IP burst. **(c)** a cache hit is exempt from the per-IP limit too,
    so an abuser hammering an *already-cached* brand can still grow
    `checker_submissions` rows at $0 (no spend, one shared analysis) — a far
    cheaper surface than fresh runs; making the per-IP cap count cache hits would
    429 a hammered-then-cached brand's own legitimate cache hits and break their
    email gate, so cache hits stay exempt.
22. **The checker cost-cap's window and kind scope are not test-pinned**
    (verify-lens finding, session 12, accepted as a minor). No test feeds the
    cap an out-of-24h-window response or a non-checker (`kind='mvp'`) response
    cost, so a regression that widened/narrowed the rolling window or dropped
    the `kind='checker'` filter would still pass green. The guard itself is
    deletion-tested; only these two boundary dimensions are unpinned. Add the
    two cases when next touching `backend/tests/test_checker_ratelimit.py`
    (P5.7 retunes `_EST_CHECKER_RUN_COST_USD` — a natural moment).
23. **Real-engine costs are approximate until P5.11's week-1 read** (P5.7,
    session 13). The pinned price table (`gemini-2.5-flash` $0.30/$2.50 per
    1M in/out; Perplexity `sonar` $1/$1) came from model knowledge, not a
    live vendor read, and `cost_usd` omits per-request search/grounding
    fees and Gemini thinking tokens — so real checker runs will cost
    somewhat MORE than recorded. `_EST_CHECKER_RUN_COST_USD` (the cost-cap
    projection) needs the same retune, and debt #22's two boundary tests
    come due at the same touch. Operator item B2 covers the price
    verification.
24. **The waitlist endpoint is a third public unauthenticated write path**
    (P5.13, session 13, verify-lens advisories, accepted): per-IP 10/hour
    keyed on the client-controlled first XFF hop (same accepted posture as
    #2/#21b); no global daily cap and no per-email cap (duplicates don't
    consume quota — an IP-rotating abuser can grow `waitlist_signups`
    unboundedly at $0); the email column has no length cap. When emails are
    ENABLED, each new signup also triggers two outbound sends — a
    mail-bomb-ish lever bounded only by the per-IP cap. Fine for launch
    volume; add a global signups/day cap when the checker goes loud.
25. **The methodology page's prose can drift silently** (P5.10, session 13,
    verify-lens advisories, accepted): the 12 prompts/version/engines are
    drift-proof (generated artifact), but `score_formula.description` is a
    hand-authored string in `scripts/gen_methodology.py`, and the CAVEATS /
    ENGINE_LABELS copy lives as literals in `page.tsx` — a scoring or
    caching change would not update them. Cheap mitigation when next
    touched: assert the cache-hours and formula strings against
    `app.config` values in the generator.
26. **Gemini grounding is disabled in practice until the operator enables
    billing** (2026-07-10 prod incident, commit `7ff580f`). The free-tier
    key has zero `google_search` grounding quota (429 on every model), so
    the adapter's grounded-first attempt falls back ungrounded and memos
    process-wide; prod Gemini answers are labeled `:ungrounded`. The
    "4 real engines with grounding" promise (roadmap 2b, methodology page)
    is 3.75/4 honest until operator item B2(a) lands: enable billing →
    redeploy → grounded re-activates with no code change. Also: lite-tier
    prices ($0.10/$0.40 per 1M) are pinned UNVERIFIED (folds into #23), and
    ListModels is NOT an availability signal — only a real generateContent
    probe is (the retired `gemini-2.5-flash` was still listed).
27. **KYC-stage spend is invisible to every cost control** (2026-07-28,
    discovery+KYC pass, surfaced while implementing step 3 of
    `discovery-kyc-improvements.md`): `generate_kyc` discards
    `result.cost_usd`, and the only dollar cap sums the *execute* step's
    `responses.cost_usd` against `checker_daily_usd_cap` ($5 per rolling 24h,
    `config.py` / `rate_limit.py`). So no KYC call has ever counted toward a
    cap. That was already true before this change; step 3 adds at most one
    extra ~$0.01 retry on failure paths only, which does not move a cap
    nothing feeds. Recording KYC cost is worth doing, but it *re-tunes* what
    the $5 cap actually measures, so it deserves its own change with its own
    review rather than riding along here.
28. **`_is_html` fails open on a missing Content-Type** (superseded by #30) (2026-07-28, step 4 of
    `discovery-kyc-improvements.md`, accepted): a 200 that declares no type is
    parsed as HTML. Deliberate — it matches `net_guard`'s stance of treating an
    unresolvable host as public so CI and offline dev keep working, and many
    respx fixtures set no header — but it means a header-less PDF still reaches
    BeautifulSoup. Sniffing the first bytes for `%PDF`/magic numbers would
    close it if a real site ever hits this.
29. **Steps 2b and 6 of `discovery-kyc-improvements.md` are specified but not
    built** (2026-07-28): Turkish suffix-aware matching and recording the
    site's language. Not debt in the "we cut a corner" sense — they revive
    roadmap §2c scope that the operator parked on 2026-07-10, and that call is
    not engineering's to make. Listed here so the gap stays visible rather than
    quietly forgotten. `test_footprint.py` pins the current (2a-only) suffix
    behaviour, so approving 2b starts by changing a test that says exactly what
    it does today.
30. **`_is_html` fail-open is now backed by a byte sniff — #28 is closed for the
    formats that matter** (2026-08-01, `pipeline-quality-plan.md` D2). A
    header-less response whose first bytes are `%PDF`, a zip/office container,
    PNG/GIF/JPEG, gzip, RIFF or PostScript — or that contains a NUL in the first
    512 bytes — is skipped. What remains open: a header-less binary format
    *not* on that list still reaches BeautifulSoup, and a genuinely UTF-16
    encoded page is now misread as binary (accepted: vanishingly rare on the
    public web, and parsing a PDF as page copy is the failure we actually saw).
31. **SPA bundle extraction still welds object punctuation onto real copy**
    (2026-08-01, measured live on beyondtech.com.tr): the string-literal
    extractor drops minified code and framework diagnostics, but a span that
    straddles an object literal arrives as `...tasarlarız.`,pillars:[{num:`01`...`.
    It is cosmetic — an LLM reads through it — and the obvious fix (reject any
    literal containing a backtick) was measured and **rejected**: it took the
    corpus from 20 000 chars to 1 751 by deleting the site's real Turkish copy.
    A proper fix parses the bundle rather than regexing it, which is a different
    (and much larger) piece of work.
32. **The prompt category filter is a heuristic, and says so** (2026-08-01,
    `pipeline-quality-plan.md` P1): phrases with digits, spec symbols, attribute
    tails ("payload capacity") or bare hyphenated adjectives ("anti-armor") are
    rejected, but nothing separates "fiber optic" (an attribute) from "fiber
    optics" (a category). The actual fix is `KYC.category`, which *asks* for the
    category — the filter only protects the path where the model does not
    supply one. Watch: a legitimate category containing a digit ("5G antennas",
    "3D printers") is currently rejected. If real profiles hit this, narrow the
    digit rule to model-code shapes (letter+digit runs) instead of any digit.
33. **Grounding's 1 000-character floor is a guess** (2026-08-01,
    `pipeline-quality-plan.md` K4): below `MIN_GROUNDING_CHARS` nothing is
    dropped, on the principle that a thin crawl cannot prove a negative. It also
    happens to be what keeps DRY_RUN's fictional profile intact against
    `example.com`. The number was chosen by reasoning, not by measurement — if a
    real one-page site ever ships a hallucinated alias through this door, tune it
    with data rather than by feel.
34. **The SERP score is binary and unweighted, exactly like the MVP GEO score**
    (2026-08-03, ADR-28): `serp_score` is `hits / measured`, so a domain hit at
    rank 1 and a snippet mention at rank 18 count identically. `detect` already
    records the rank of the brand's first appearance on every page and stores it
    on the `serp_checks` row, so the evidence to weight by position is captured —
    it is the scoring that deliberately ignores it. Position weighting is the
    obvious next lever, and the sibling of the roadmap's weighted AI-visibility
    score; left unbuilt on purpose so the first cut ships one honest number.
35. **A SERP number is a one-shot snapshot that nothing ever re-measures**
    (2026-08-03, ADR-28): `run_serp` fires once, at analysis time; nothing
    schedules a re-run, so the number ages silently the moment the results move
    under it — which, for a search page, is continuously. Each `serp_checks` row
    carries the moment it was taken (ADR-28: a SERP "only means anything with the
    moment attached"), but there is no second reading to compare it against. Rank
    tracking over time is the product this eventually becomes; today it is a
    point measurement wearing a timestamp.
36. **`serp_query_count` is a politeness budget chosen by reasoning, not
    measurement** (2026-08-03, ADR-28): the default is 6 (`config.py`,
    `DEFAULT_QUERY_COUNT`). Each query is a single HTTP GET to the operator's
    *own* SearXNG instance, so — unlike the LLM panel — there is no vendor invoice
    to tune the count against; the only cost signals are the instance's upstream
    rate-limits and the worker latency the queries add to a run. 6 is a guess at
    "enough shapes to be representative without hammering a self-hosted box";
    retune it against a real instance's behaviour if one ever complains.
37. **Domain matching is host-suffix based, not registrable-domain based**
    (2026-08-03, ADR-28): `_is_own_site` counts a result as the company's own
    site when its host equals — or is a dotted subdomain of — the exact host of
    the submitted URL (`www.` stripped). There is no public-suffix list in the
    dependency tree, so no eTLD+1 is ever computed. The error direction is at
    least conservative: it *under*-matches and never fabricates a hit — a company
    whose ranking pages live on a sibling ccTLD (`example.de` when `example.com`
    was submitted), or on the apex when a subdomain was submitted, is simply not
    recognised as a domain hit and falls through to text detection or a miss. But
    it does mean the domain signal is only ever as complete as the one host the
    buyer typed. A real PSL (e.g. `publicsuffix2`) is the fix if multi-domain
    brands turn out to matter.
38. **The measurable/miss split trusts `unresponsive_engines`** (2026-08-03,
    ADR-28): `SerpPage.measurable` (`serp/base.py`) is `bool(results) or not
    unresponsive_engines`, so an empty page is dropped from the denominator only
    when the instance *told us* which engines refused. An instance that returns
    an empty result list **without** populating that field is scored as a genuine
    miss (`measured += 1`, `hits` unchanged). The realistic way to trip this is a
    misconfigured instance with zero engines enabled, or a future SearXNG that
    stops emitting the field — both are indistinguishable from "searched and
    found nothing". This whole feature is organised against manufacturing a zero,
    and this is the one seam where a manufactured zero can still slip in; accepted
    because "results present, no failures reported" genuinely has to read as an
    answer, and a healthy instance really does return empty pages that mean
    exactly that.
39. **The query shapes are hardcoded English, so home-market visibility can be
    under-measured** (2026-08-03, ADR-28, found while reading the code):
    `_QUERY_SHAPES` and `_LOCATION_SHAPE` ("best {topic}", "best {topic} in
    {location}") are English literals, and `serp_language` defaults to `"en"`.
    The language is at least an operator setting; the shapes are not — so even
    pointing the instance at Turkish results would still search English keyword
    forms. The irony is on the label: `_LOCATION_SHAPE`'s own comment motivates
    itself with "a Turkish manufacturer that ranks nowhere globally may well own
    its home results", yet that manufacturer is queried in English. This is the
    SERP-side twin of debt #19a / #29 (the pipeline's English-centric
    assumptions). Localising the shapes — probably keyed off the site language
    that #29 would record — is the real fix; declined here to keep the first cut
    to one language.
40. **The integration tests pin one SearXNG image tag, so the PR gate cannot
    catch upstream drift on its own** (2026-08-03, ADR-28): `serp.yml`'s
    `integration` job — the one that runs on `pull_request` — boots a
    fixture-backed instance from a pinned image tag, which is exactly what makes
    it deterministic, and therefore blind to a breaking change in a newer
    SearXNG. The `upstream` job re-runs the same suite against
    `searxng/searxng:latest`, but it is gated to `schedule`/`workflow_dispatch`
    only (so it runs from the default branch), deliberately outside the PR gate
    so an upstream release pages the team instead of reddening an unrelated PR —
    which is why `SERP` is in `notify.yml`'s `workflows:` list. The accepted
    consequence: a SearXNG release that breaks our adapter is caught by the
    nightly, on a lag of up to a day, never by whichever PR happens to be open
    when it lands.
41. **Own-site domain matching compares raw host strings, so a Unicode domain
    can miss** (2026-08-03, ADR-28, found by review before merge): `_host` in
    `pipeline/serp_visibility.py` lowercases `urlparse(...).hostname` and
    `_is_own_site` compares the result as a plain string. It applies no IDNA
    normalisation, so a submitted URL written in Unicode (`https://köln.example`)
    and a SERP result the instance returns in punycode
    (`https://xn--kln-sna.example`) are two different strings and the company's
    own site is not recognised as its own. The failure is silent and one-sided —
    it under-matches, never fabricates a hit, and the result usually still
    catches on the text match — but the domain signal, which is the strongest one
    this feature has, quietly stops working for exactly the non-ASCII brands the
    product's Turkish wedge is aimed at. The fix is one `.encode("idna")` on
    both sides; not applied here only because it wants a test corpus of real IDN
    sites rather than an invented one.
42. **The SERP response is read without a byte cap** (2026-08-03, ADR-28, found
    by review before merge): `SearxngSource.search` calls `response.json()` on
    whatever the instance sends, with no equivalent of discovery's
    `MAX_PAGE_BYTES`. Post-parse the adapter is careful — `max_results` caps the
    rows and every field is length-capped — but the whole body is materialised in
    the worker first. It is deliberately not treated as a threat (the instance is
    the operator's own container, not a stranger's URL — that asymmetry is the
    same one that justifies skipping `net_guard` here), so this is an
    inconsistency with `discovery`'s posture rather than a live risk: a
    misbehaving or compromised instance could make a worker allocate a lot of
    memory. A streamed read with a cap would close it cheaply if the instance
    ever stops being trusted infrastructure.
43. **`DRY_RUN` forces the mock SERP source, so real search cannot be rehearsed
    with a mocked panel** (2026-08-03, ADR-29, found by trying it): the registry
    checks `dry_run` *before* `serp_base_url`, so a stack with `DRY_RUN=1` and a
    perfectly good instance configured still gets `MockSerpSource`. That
    coupling is deliberate — DRY_RUN promises `$0` and a reproducible run, and
    CI's `stack` job asserts `source == "mock"` — but it conflates "spend no
    money" with "make no network calls", and SERP against an instance you host
    yourself costs nothing. The practical cost showed up immediately: the only
    way to exercise the real-SERP path end to end is `DRY_RUN=0`, which also
    turns the LLM panel real and therefore costs money, so the pre-deploy
    rehearsal had to verify the adapter directly instead of through the pipeline.
    A third mode (`SERP_DRY_RUN`, or letting an explicit base URL win) would fix
    it; not done here because it widens the run-mode matrix CI has to pin, and
    the production path (`DRY_RUN=0`) is unaffected.
44. **Two of the four search engines are refused from this egress IP, and which
    two varies per query** (2026-08-03, ADR-29, measured): across 8 buyer-style
    queries `brave` and `startpage` refused every time while `google cse`
    answered every time — but a later probe had `brave` answering and
    `duckduckgo` refusing. So `unresponsive_engines` is non-empty on most stored
    rows, and in practice the SERP number leans on `google cse`. Results are
    still plentiful (20–30 per page) so pages stay measurable, and this is
    recorded rather than fixed because the honest reading is "we depend on one
    engine more than the panel suggests" — worth knowing before anyone reads the
    score as a four-engine consensus. If Google CSE ever starts refusing too,
    expect pages to go unmeasurable rather than to silently report zeros; that is
    the design working, but it will look like an outage.
45. **The audit sees at most six pages, but its findings read as site-wide**
    (2026-08-03, ADR-31): `discovery` crawls the homepage plus `MAX_LINKS` (5)
    scored links, so every check except `ai_crawler_access` and `sitemap` is
    really a statement about those pages — and the page-level ones
    (`indexable`, `thin_content`, `server_rendered_content`, `title_present`,
    `h1_present`, `lang_declared`, `canonical`, `meta_description`) are
    homepage-only. A site with a perfect homepage and 400 thin product pages
    grades A. The check titles do not currently carry that caveat, which is the
    honest gap: the numbers are right about what they measured and the wording
    implies more. Cheapest fix is wording; the real fix is sampling more pages,
    which costs crawl budget the pipeline deliberately caps.
46. **The severity weights are editorial and will not survive contact with data**
    (2026-08-03, ADR-31): critical/important/minor = 5/3/1 was chosen by
    reasoning, and the grade cap exists precisely because we do not trust the
    weighted average on its own. Three tiers are defensible and publishable,
    which is why they were picked over per-check coefficients — but nothing has
    yet been calibrated against real outcomes, because the outcome that would
    calibrate them (does a better grade actually correlate with a better GEO
    score?) needs a corpus of audited sites we do not have yet. `seo_checks` is
    indexed on `(check_id, status)` specifically so that question becomes
    answerable once there is data.
47. **`discovery` now parses each page one extra time** (2026-08-03, ADR-31):
    `_page_audit` runs its own `BeautifulSoup` pass alongside the existing
    `_visible_blocks` / `_jsonld_text` / `_meta_text` passes. That is a fourth
    parse of the same bytes per page, for up to six pages. Parsing once and
    sharing the soup is a real win and was deliberately left out of this change,
    because it would touch the honesty-critical text path that produces the GEO
    score in the same diff that adds a new feature.
48. **No `llms.txt` check** (2026-08-03, ADR-31): the emerging convention for
    telling an LLM what a site is about. Left out because adoption is still thin
    and a check nobody passes teaches a customer nothing — but if it becomes
    real, it is one more cheap same-origin fetch and belongs next to
    `robots.txt`.
49. **Password reset has no endpoint, so it ships no screen** (2026-08-03,
    account screens, PR #13): the auth router is signup / login / refresh /
    logout / me and nothing else. The `/forgot-password` route and the "Forgot
    password?" link on `/login` were **removed** rather than shipped, because a
    form whose only possible answer is FastAPI's `404 {"detail":"Not Found"}` —
    rendered verbatim in a red box — is worse than no form. What survives is
    `requestPasswordReset` in `lib/auth.ts`, unrouted and unreferenced by any
    screen, kept as the contract the endpoint is expected to meet and pinned by
    two tests in `auth.test.ts`. Repaying this is: write the endpoint, then
    restore the page and the link (both are one `git revert` away — see the
    session log). One requirement carries over in the client's comment: an
    unknown address must answer exactly like a known one, or the endpoint
    becomes a way to test which emails are registered.
50. **There are no terms, so sign-up asks for no agreement** (2026-08-03,
    account screens, PR #13): the form shipped a **required** checkbox pointing
    at a `/terms` page that said, honestly, that nothing on it was binding. A
    forced consent to an unwritten document is not consent, and merging `main`
    deploys. The checkbox, `validateTermsAccepted`, `components/Checkbox.tsx`
    and the placeholder page were all removed; a test asserts the form offers no
    checkbox and no terms link, so putting one back is a deliberate act. **This
    is a legal/product blocker, not an engineering one** — the text has to be
    written before an account can be conditioned on it.
51. **Every cold load POSTs `/api/v1/auth/refresh`, anonymous visitors
    included** (2026-08-03, account screens, PR #13): `AuthProvider.restore()`
    runs on every page, and a script cannot read an httpOnly cookie, so asking
    is the only way to learn whether a session exists. The cost lands on `/` and
    `/checker` — routes that are about to go public and carry no rate limit of
    their own — as one auth POST plus a 401 per visit. The fix is a
    non-httpOnly `has_session` hint cookie set at login and cleared at logout,
    letting the client skip the call when there is obviously no session; it
    touches the backend (`auth_cookies.py`) as well as `AuthProvider`, which is
    why it is not in PR #13. **Close this before the checker goes loud.**
52. **An account grants nothing** (2026-08-03, account screens, PR #13): no
    route is protected, and there is no signed-in destination — `login/page.tsx`
    pushes to `/`, where the header shows the email. So the sign-up CTA now sits
    on every page, including `/checker`, next to the launch wedge, offering
    something that does nothing yet. Recorded as a **timing** question for the
    operator rather than a defect: the code is ready and can sit ready. Closing
    it means either the first thing worth signing in for (saved analyses,
    history) or holding the header CTA back until there is one.

    **REPAID, session 22 (2026-08-05).** An account now grants something
    concrete: routes are guarded (`RequireAuth`), signing in lands on
    `/dashboard`, and the **Admin Panel** is a real signed-in destination — an
    owner can invite a colleague, assign and change their role, disable,
    re-enable or remove them, and read the audit trail of all of it. The
    remaining half of the original complaint — *saved analyses and history* —
    is M4's, and is tracked in [backlog.md](backlog.md) rather than here.
53. **The cross-tab refresh guard degrades where Web Locks are missing**
    (2026-08-03, account screens, PR #13): `lib/session.ts` serialises rotation
    across tabs with `navigator.locks`, which closes the race where two tabs
    cold-loading together replay the same consumed refresh token and the backend
    revokes the whole family. Browsers without it (Safari before 15.4, Firefox
    before 96) fall back to the per-tab single-flight promise and can still hit
    that race. Deliberate: a rotation that never runs would be worse than one
    that can race, and the fallback is the behaviour every tab had before. A
    BroadcastChannel leader would cover them, at the cost of an election and
    token material crossing a channel (ADR-32, "Rejected").
54. **PR #11 (measured/simulated GEO pivot) is live in `main` and entirely
    undocumented** (2026-08-05, session 20 — found during re-planning, merged
    2026-08-04 outside the session process). What it changed: the runner's
    execute step is now `execute_measured` — `geo_mode=measured` (Tavily
    search → grounded OpenRouter answer → audit record) or `simulated`
    (OpenRouter-only) — with `geo_records` (migration 0011) + per-analysis
    citation summaries, an interventions engine
    (`pipeline/interventions.py` + `data/intervention_library.json`), a
    reliability auditor (`pipeline/reliability.py`), and OpenRouter/Tavily
    providers. What that breaks in the docs: architecture.md §1–2 and the
    README describe the old 4-engine panel execute; recorded test counts
    predate it; `pipeline/execute.py` remains in-tree but unwired; ADR/
    session/plan records don't exist. **Operational edge: with `DRY_RUN=0`
    and `geo_mode=measured` (the default), missing `OPEN_ROUTER_KEY` /
    `TAVILY_API_KEY` fails live analyses — verify prod `deploy/.env`
    (operator B7).** Repay by: a retroactive ADR + plan card, doc sync
    against verified behaviour, and a decision on `execute.py` (delete or
    re-wire as the multi-engine surface — roadmap M4 wants the latter).

    **PARTIALLY REPAID, session 21 (2026-08-05).** Done: the retroactive
    **ADR-34** is written, from the merged code read against a running stack
    rather than from the PR description, and it records two things the PR did
    not intend — that the GEO score changed meaning *and scale* across
    2026-07-29 (0–100 composite now, 0–1 mention rate before, same column), and
    that cost accounting silently broke (fixed separately, `ed384a1`; see
    **#58**). The **B7** key edge is verified satisfied in production and
    ticked. `execute.py` is confirmed dead on every runtime path and
    deliberately **kept** — that decision is now recorded in ADR-34 rather than
    left open, and belongs to M4. **Still open:** the doc sync. Session 22's docs
    inventory audit pinned exactly what is wrong, so this no longer needs
    rediscovering:

    - `docs/architecture.md` §1's provider diagram, §2's steps 4/5/6, the
      DRY_RUN / mock-path section and the result-shape line all still describe
      the four-engine panel and the `footprints / total` score. The live path is
      measured/simulated (Tavily + OpenRouter, **one Response per prompt**, a
      composite `geo_score`, a `geo_records` twin). §3 — the Admin Panel section
      added in session 22 — is accurate and must be left alone.
    - `docs/architecture.md`'s table list omits `geo_records`.
    - `docs/test-suite.md`'s scoring and execute bullets, and two rows of its
      acceptance map, teach the pre-PR-#11 definition of done.
    - `docs/02-mvp.md` §5/§8 (scoring formula) and §3 step 5 (engines) also
      contradict the live pipeline — but that doc is cited by `session-rules.md`
      as the **scope authority**, so rewriting it changes what that authority
      *is*. That is an operator decision, recorded in the session-22 log's
      docs-audit section, not something to fix in passing. (FR-6's "two routes"
      claim is plainly wrong regardless and can go either way.)

    The README half **is** repaid as of session 22: its mini-map and
    Make-target rows now describe the real surface.
55. **The Site Audit backend (PR #23) is merged but undocumented beyond
    `site-audit-integration.md`, unhardened, and unreachable** (2026-08-05,
    session 20; merged 2026-08-03/04 outside the session process). It ships
    real capability — `seo_projects`/`site_audits`/`site_audit_pages`,
    authenticated APIs, a Chromium-rendering crawler with its own queue/
    worker — but: no ADR or plan card names it; its own doc lists unresolved
    production requirements (egress isolation, non-root Chromium, transfer
    budgets, retries, quotas, migration gate, deploy verification); the
    dedicated worker is in no compose file, so nothing runs it in prod; and
    no frontend reaches its APIs. Deliberately scheduled rather than hidden:
    productization + hardening is **roadmap M3 (Phase 9)**; the retroactive
    ADR should land with the first M3 card.

56. **A whole product shell shipped undocumented — PRs #24 and #25**
    (2026-08-05, session 21; both merged 2026-08-05 outside the session
    process, and both auto-deployed to production the same hour). Together
    they add ~5,800 lines of frontend across 64 files: a Semrush-style
    `AppShell` with a section/flyout navigation model
    (`frontend/lib/shell-nav.ts`), an AI-Visibility surface
    (`app/ai-visibility/**` + `components/ai-visibility/**`), a
    Search-Visibility overview, the Site Audit UI that finally reaches
    #55's backend (`components/site-audit/**`), an
    `AnalysisSessionProvider`, and a rewritten landing page. It carries its
    own tests (frontend is now 205 across 41 files, up from the 65 the docs
    still claim) — so this is *undocumented*, not *untested*. What is
    missing is the same as #54/#55: no ADR, no plan card, no session log,
    and no roadmap entry — yet `shell-nav.ts` is a **product information
    architecture**, naming ten sections (Backlinks, Analytics, Reports,
    Settings, Position Tracking, Keyword Magic…) whose `na` badges are now
    a public promise the roadmap did not make. Two concrete consequences:
    (a) the M1–M9 milestone names and this nav must be reconciled, or the
    product says one thing and the plan another; (b) the Site Audit UI makes
    #55's unhardened backend **user-reachable**, which raises that item's
    priority rather than lowering it. Repay: a retroactive ADR + plan card
    covering the shell and its IA, folded into the first M3 (Phase 9) card
    alongside #55's, and a roadmap reconciliation pass at the next planning
    checkpoint. Scheduled, not blamed — but this is the third such merge in
    three days, and the pattern itself is the debt.

57. **The formatter is not gated, only the linter is** (2026-08-05, session
    21). CI's backend job runs `ruff check` but never `ruff format --check`,
    and the frontend job runs `eslint` but never `prettier --check` — while
    `make fmt` exists and formats both. So a file can sit unformatted
    indefinitely: `backend/app/db/models.py` was already unformatted on `main`
    before this session touched it (a `GeoRecord` column left in three-line
    form by PR #11 that fits on one at the configured 100-char width), and it
    took an unrelated `ruff format` run to notice. Consequences are small but
    compounding: unrelated reformat noise rides along in the next diff that
    happens to run the formatter, which is exactly what happened here. The fix
    is one step in each CI job (`ruff format --check .`,
    `npx prettier --check .`) — cheap, but it will fail on whatever is
    unformatted today, so it wants its own small PR rather than a ride-along
    in a feature branch. Not urgent; do it before the Phase 7 lanes start
    running in parallel, because that is when reformat noise starts causing
    real merge conflicts.

    **PARTIALLY REPAID, session 22 (2026-08-05; ADR-40).** There is now a
    formatting gate — `.github/scripts/format_changed.sh`, run as its own CI
    job — but it is scoped to the files a branch changed rather than the repo.
    That was the only option that could land inside a feature branch: the
    repo-wide version fails on ~47 backend files today, which is precisely the
    "own small PR" this item asks for. **What remains open is exactly that
    sweep.** The gate means the unformatted set can only shrink from here, and
    a PR that edits an unformatted file must now format it.

58. **The Tavily per-search price is a pinned guess** (2026-08-05, session 21,
    with the cost-recording fix `ed384a1`). Search spend is now counted into
    `responses.cost_usd` — but at `TAVILY_SEARCH_USD`, default **$0.008**,
    which is **UNVERIFIED**. Tavily bills in plan-dependent API credits that
    the application cannot read, and no agent here can see an invoice. The
    number is deliberately set high, because the direction of the error
    matters: an over-estimate makes a cost cap trip early (annoying, safe), an
    under-estimate makes it trip late (expensive). Same posture as #23's
    unverified flash-lite prices, and it wants the same fix — one look at a
    real invoice, then correct `TAVILY_SEARCH_USD` in `deploy/.env`. Operator
    item **B9**. Note the asymmetry: OpenRouter reports its own per-call cost
    in the response, so only the search leg is guessed.

    A second, subtler edge rides with it. The fix makes
    `CHECKER_DAILY_USD_CAP` **functional for the first time on the measured
    path** — it has been summing a column of zeros. Nothing changes today
    (`CHECKER_ENABLED=0`, so the checker is dark), but whoever performs the
    P5.11 go-live should know the cap is now live, is denominated partly in a
    guessed price, and will bite at `$5.00/day` of *estimated* spend.

59. **A failed audit write loses the event, not the request** (2026-08-05,
    session 22, P7.3). `audit.emit` catches every exception it can raise and
    returns `None` with a logged warning. That is the right trade at the
    request level — an audit write failing must not turn a successful password
    change into a 500, because the change already happened — but it means the
    audit trail's completeness rests on the database being healthy at the
    moment of every write. There is no outbox, no retry, and no counter that
    would tell an operator how many events were dropped. Consequence, stated
    plainly: the trail is *tamper-evident* (ADR-38) but not *loss-evident*, and
    a compliance claim built on it later has to account for that gap. The fix
    is an outbox table written in the same transaction and drained by the
    worker, which is stage A9's hardening card. Not urgent while the volume is
    this low; it becomes urgent the first time somebody cites the log as
    complete.

60. **Workspace-scoped roles are honoured at org grain** (2026-08-05, session
    22, P7.2/P7.4). `permissions.py` defines Manager, Editor, Analyst, Viewer
    and Guest as workspace-scoped roles, and `admin-panel-plan.md` §5 models
    permission as `role capability ∩ scope grant`. Only the first half exists:
    a membership carries one role for the whole organization, `workspace_grants`
    was never created, and `invitations.workspace_id` is written but read by
    nothing. So an Editor in an agency with three client workspaces is an
    Editor in all three. That is *safe* — nobody gets more than their role
    allows — but it is not the model the plan promises, and the wedge
    (differentiator D4: workspace-per-client with free Guest seats) depends on
    the missing half. The column is in place so closing it needs no migration
    on a populated table. Scheduled with the workspace management screens.

61. **The organization profile is read-only** (2026-08-05, session 22, P7.4).
    `GET /api/v1/admin/organization` exists; there is no PATCH. An org cannot
    be renamed, its slug cannot change, and there is no logo or branding field
    in use — so the personal org created at signup keeps its
    `"<email-local-part>'s organization"` name forever unless somebody edits
    the database. `ORG_UPDATE` is already defined and granted to Admin and
    Owner, so this is a route and a form, not a design question. Small, and
    visible to every single user, which is the argument for doing it early.

62. **The frontend has no formatter contract, and `make fmt` will damage it**
    (2026-08-05, session 22). `make fmt` runs `npx prettier --write .` over the
    whole frontend — and there is **no `.prettierrc` anywhere in the repo**, so
    that command formats to Prettier's *defaults*: semicolons and double
    quotes. The code that exists uses neither. Running the documented format
    target would therefore rewrite the entire frontend into a style nobody
    chose, in one unreviewable commit. Nobody has hit it because nobody has run
    it. Measured this session: at `printWidth` 80 / 90 / 100 with
    `semi: false, singleQuote: true`, **61 / 55 / 68 files** respectively still
    differ — so there is no config that is a no-op either; adopting one is a
    real reformat and wants its own PR. Consequences: the CI formatting gate
    added this session (ADR-40) deliberately **skips** frontend files and says
    so, activating by itself the moment a config file appears. Repay by
    choosing a config (matching the dominant style — no semicolons, single
    quotes — and whichever width the team prefers), reformatting in a dedicated
    PR, and letting the gate switch on. Until then eslint at `--max-warnings 0`
    is the frontend's only automated style gate, which is what it has always
    been.

63. **The fail-closed tenancy seam ADR-35 describes is not wired — isolation is
    per-route discipline** (2026-08-08, session 24, found by a code-vs-docs
    audit). `app/services/tenancy.py` defines `scoped()` (raises without an org
    context rather than returning an unfiltered statement) and
    `readable_analysis()` (the single home of the NULL-is-public rule). **Both
    have zero call sites.** No route and no service calls either; `GET
    /analyses/{id}` uses bare `get_analysis()`. Tenant isolation is real today
    — the `requires(...)` / `OrgContext` dependency in
    `app/api/org_dependencies.py` resolves and membership-verifies the org on
    every request, and each route filters by `org.require_org_id` itself — but
    that is discipline, not a seam: **a route that forgets to filter compiles,
    passes review, and leaks.** This is the highest-risk item on this list
    because three documents asserted the opposite (ADR-35,
    `architecture-target.md`, the P7.1 card), so a reader had every reason to
    believe the guardrail was there. All three are corrected as of this session.
    Repay in P7.9/A9: the cross-tenant leakage suite is the exit gate that
    would have caught this, and it should be written to fail if a tenant-owned
    query is reachable without an org filter — not merely to spot-check a few
    routes. Until then, treat every new tenant-scoped query as needing its own
    explicit `org_id` filter, because nothing does it for you.

    **Update 2026-08-09 (session 26) — substantially repaid, and deliberately
    not closed.** Both functions now have call sites: `readable_analysis()` in
    `GET /analyses/{id}`, and `scoped()` in `services.analyses.
    list_org_analyses` (ADR-49). More importantly, **the leakage suite exists**
    (`tests/test_cross_tenant_leakage.py`, 34 tests) and it was built to the
    instruction above rather than as a spot-check: every operation is read out
    of the live OpenAPI schema, an unclassified route **fails the suite**, and
    every probe is a pair so it cannot pass vacuously.

    What keeps this open is the gap between "no route leaks" and "no query can".
    The suite proves the first, which is the guarantee the milestone's exit
    criterion asks for. The second needs scoping enforced at the query layer,
    and a service function with a missing filter that no route reaches today is
    still invisible — see **#90**. The standing instruction is unchanged: every
    new tenant-scoped query needs its own explicit `org_id` filter.

64. **Three Site Audits are stranded `queued` in production and need operator
    cleanup** (2026-08-08, session 24). `31eba473…`, `410c31d7…`, `35e06651…`,
    created 2026-08-05/06, zero pages each. They were enqueued through a UI
    that shipped in PRs #24/#25 while no site-audit worker was ever added to
    `deploy/docker-compose.prod.yml`, so nothing has ever drained them and
    nothing ever will in their current state. Session 24 gated the enqueue so
    no more accumulate, but **it deliberately did not touch the rows**:
    mutating production data is an operator action, and there are no database
    backups. Repay by deciding their fate (mark failed with a reason, or
    delete) — see [operator-expected.md](operator-expected.md). Note the
    backlog's premise that both tables held **zero** rows was stale by the time
    it was acted on; measure before trusting it again.

65. **The site-audit worker holds every secret — its isolation is design, not
    boundary** (2026-08-08, session 24). `docs/site-audit-integration.md`
    claimed the audit worker receives only its database URL and `SITE_AUDIT_*`
    settings. It calls the shared `get_settings()`, so it would hold
    `jwt_secret_key` and every provider key. That claim is corrected in the doc
    now, but the gap it described is unbuilt. This matters because the audit
    worker is the one component whose whole job is to point a browser at
    arbitrary third-party URLs — the highest-exposure process in the system
    holding the widest secret set, on a box shared with four other tenants.
    Repay before `SITE_AUDIT_ENABLED` is ever turned on: an `audit-runtime`
    image with a split settings object. Tracked in M3 alongside
    `deploy-site-audit-worker`, `site-audit-chromium-image-missing` and
    `site-audit-egress-isolation` — none of which should land without this one.

66. **Site Audit's off-state is discovered reactively, by catching a 404**
    (2026-08-08, session 24). There is no runtime feature-flag endpoint, so the
    frontend cannot know `SITE_AUDIT_ENABLED` (or `BACKLINKS_ENABLED`) at first
    paint; it learns by attempting the action and handling the refusal. That is
    honest but late. The proper repair is the `feature-flags-system` backlog
    item (DB-backed flags, global + per-org, audited flips) with a small read
    endpoint the shell can consume — which also retires the env-boolean
    kill-switches that currently need a redeploy to flip.

67. **The sessions list cannot tell you which device a session is** (2026-08-08,
    session 24, P7.5). `auth_sessions` stores no IP, user-agent or device name,
    so "Devices & sessions" shows started / last-active / expires and nothing a
    human recognises. Adding columns needs a migration, which this session
    deliberately deferred (no DB backups). Repay with the migration-bearing half
    of A5, alongside password reset and MFA — a session list you cannot identify
    a device in is a weak security control, because the user cannot tell their
    own laptop from an intruder's.

68. **A revoked membership is only noticed on the next `/auth/me`**
    (2026-08-08, session 24, P7.5). The org switcher stores the active org
    client-side and reconciles it against `/auth/me` on cold load, sign-in and
    switch. If a user's membership in the *currently selected* org is revoked
    mid-session, other org-scoped endpoints 403 until the next `/me` refresh.
    Not a leakage risk — the server verifies membership on every request, which
    is why the failure mode is a 403 and not a read — but it is a confusing
    dead-end for the user. Repay with a global 403 interceptor that clears the
    active org and re-fetches `/me`.

69. **`/auth/me` does an N+1 over memberships** (2026-08-08, session 24, P7.5).
    One `session.get(Organization)` per membership to build the organizations
    list. N is the number of orgs a user belongs to, so this is nothing today
    and would become something for a contractor in dozens of orgs. One
    `IN`-query join when it matters.

70. **The rollback guard hardcodes a boundary SHA** (2026-08-08, session 24,
    ADR-42). `deploy/rollback.sh` refuses to rebuild a last-good SHA at or
    behind `56c1fac` (the migrate-on-boot split). The constant is documented
    and re-derivable —
    `git log -S 'sh -c "alembic upgrade head' -- deploy/docker-compose.prod.yml`
    — and a history rewrite would make the guard fail closed (refuse
    everything) until it is updated. Acceptable because `main` is
    ruleset-protected against rewrites and refusing is the safe direction, but
    it is a constant that encodes a fact about history and should be revisited
    if the deploy driver is ever rewritten.

71. ~~**Mutating paths that still emit no audit event**~~ (2026-08-08, session
    24, found by audit-coverage review; **REPAID 2026-08-09, session 26,
    ADR-48**). M1 promises "every mutating action emits an audit event." These
    did not: `track_competitor` / `untrack_competitor`, `POST /auth/refresh` —
    including, notably, the **refresh-token reuse detection** path, which
    revokes an entire session family because it believes a token was stolen and
    wrote no record that it happened — plus the checker submit, its lead gate,
    and the waitlist.

    All six now emit, and the repair changed the rule rather than just closing
    the list. "Every mutating action" is not the rule the system can keep: a
    successful refresh rotation *is* a mutation and is deliberately silent,
    because it fires four times an hour per signed-in device and would bury
    every real event under heartbeat rows. The rule is now **every mutation with
    a consequence emits, and every deliberate silence has a test asserting the
    silence** — the second half being what stopped this item from being
    invisible for four sessions.

    Residuals are **#84** (a retry loop into a 429 writes a row per retry),
    **#85** (an optional `context` that degrades attribution silently) and
    **#86** (the checker's cost trail overlaps its demand table). What is *not*
    residual: A9's audit-completeness review no longer has a backlog of missing
    emitters to work through, only `audit-emit-no-outbox` — the deliberate trade
    that an audit write failure must never 500 a request.

72. **Session 23 shipped without any of its eight close deliverables**
    (recorded 2026-08-08, session 24; **partially repaid on record**). P8.3's
    API and screens merged as PRs #33 and #34 with no session log, no ADR, no
    tech-debt entry, no operator refresh, and no next-session prompt — so
    `operator-expected.md` still told the operator that session 22's work was
    unmerged, two merges after it had shipped and deployed. Session 24
    reconstructed the log from the commit range
    ([`sessions/2026-08-06-01.md`](sessions/2026-08-06-01.md)) and repaired the
    downstream docs. **What cannot be recovered is the reasoning**: an ADR
    written by someone who was not in the room is a fabricated rationale, so
    two decisions worth recording (the single-front-door rule for projects, and
    `live`-while-dark as a nav badge) remain unwritten. This is process debt
    rather than code debt, and it is listed because it is the second time it has
    happened (PRs #11 and #23 before it, items #54/#55) and because the cost is
    silent: the code is fine, the *why* is gone.

73. **A signed-out caller can still run analyses on the anonymous funnel — no,
    they cannot, and that is the item** (2026-08-09, session 25, ADR-45).
    Recording the shape of what changed, because it is easy to misread later.
    `POST /api/v1/analyses` now requires authentication, so there is **no
    anonymous GEO analysis surface at all**. That is deliberate — the public
    funnel is `/api/v1/checker` — but it means a product decision has been made
    in code: if the operator ever wants a "try one analysis without an account"
    funnel back, it is not a config flip, it is a route change plus a decision
    about what bounds it. Nothing is broken; the debt is that the decision lives
    in a route signature and an ADR rather than in a product doc.

74. **Plan credit is never granted, so the credit half of the billing engine is
    unreachable** (2026-08-09, session 25). Every plan declares a
    `monthly_credit_usd` and nothing ever writes a `grant` ledger row, so every
    organization's balance is exactly 0. `billing.reserve()` refuses when the
    balance cannot cover an estimate — which means using it on any path with a
    non-zero estimate would refuse **every** request. That is why P7.6's
    enforcement uses `consume_quota` (counts) and `record_charge` (recording),
    and why `reserve()` is still called only from the flag-off backlink path
    whose mock estimate is $0. The credit gate is built, tested and structurally
    unusable until grants exist. Backlog: `grant-monthly-plan-credit`, which
    belongs with the Stripe lifecycle because "start of billing period" is a
    subscription concept.

75. **Usage counters have no per-org concurrency guarantee** (2026-08-09,
    session 25). `consume_quota` reads the `UsageCounter` row, adds to it, and
    flushes inside the request transaction. Two simultaneous submits from one
    organization can both read `used=4` against a limit of 5 and both commit —
    the unique constraint is on `(org_id, metric, window_start)`, which prevents
    a duplicate row but not a lost update. Worst case is one extra unit of a
    monthly allowance, which is why it is here rather than fixed today; the fix
    is `SELECT … FOR UPDATE` on the counter (Postgres-only, so the SQLite test
    path needs the usual dialect branch, as `jobs/queue.py` already does for
    `SKIP LOCKED`). Do it when quotas gate something whose unit cost is large —
    the backlink vendor adapter is the first candidate.

76. **Nothing checks the plan catalog at runtime — only in CI** (2026-08-09,
    session 25). An unseeded `plans` table now answers 503 with an honest
    message instead of pretending everyone is out of quota (ADR-45), and
    `test_migrations.py` asserts that a migrated database leaves a usable
    catalog with Free present and every metered key declared. Between those two
    there is still no *running-system* check: `scripts/check_env.py` runs at
    deploy preflight and never touches the database, and `/healthz` is a
    hardcoded literal (P7.8's `deep-health-endpoint`). Since seeding is a
    migration, the realistic failure is a restored or hand-built database rather
    than a missed deploy — which is exactly the path a **backup restore**
    (operator B13) would take. Fold the check into the deep health endpoint when
    A8 builds it.

77. ~~**The analyses a customer runs are attributed but not listable**~~
    (2026-08-09, session 25; **REPAID the same day, session 26, ADR-49**). Runs
    carried `org_id` and the only way to reach one was still the URL you were
    redirected to, so a customer who closed the tab had lost the result.
    `GET /api/v1/analyses` and the `/analyses` screen close it. Residuals **#87**
    (no supporting index — it is a migration, and migrations are gated on B13)
    and **#88** (the list does not poll; the run page it links to does).

78. **The pre-migration snapshot has never run against a real migration**
    (2026-08-09, session 25, ADR-46). `deploy.sh` now compares `alembic current`
    with `alembic heads` and dumps the database before migrating. The schema has
    been at `0018_invitations_audit_integrity` throughout, so only the *no-op*
    branch has executed in anger — verified against the live stack, where both
    revisions report `0018` and the deploy correctly skips. The branch that
    matters, the one that takes a dump and aborts the deploy when it fails, has
    been exercised only by running `backup.sh` directly. The next migration-
    bearing deploy is its first real test, which is a fine time to watch the
    deploy log rather than walk away from it. Repay by reading that log.

79. **Backups live on the same box as the database** (2026-08-09, session 25).
    `~/yanki-backups` is on the VPS whose volume it is protecting. That covers a
    bad migration, a dropped table and a mis-run backfill — the failures that
    actually happen here — and it does not survive losing the box. This is
    listed as debt rather than left to the operator item alone because the
    dangerous failure mode of a backup system is somebody believing it covers
    more than it does, and a half-covered system reads as a covered one.
    Closing it needs a destination and a credential (operator **B13**);
    `deploy/BACKUP.md` carries two one-line options.

80. **Nothing runs `backup.sh` on a timer** (2026-08-09, session 25). The
    pre-migration hook fires only on a deploy that changes the schema, so
    between schema changes there is no new dump at all. One cron line closes it
    and it is in `deploy/BACKUP.md`; installing it is a change to the live box's
    schedule and it needs the retention decision, which interacts with a PII
    retention policy that does not exist (`pii-retention-and-erasure`).

81. **A wedged worker is now visible and still not restarted** (2026-08-09,
    session 25, ADR-47). The heartbeat + compose healthcheck make a `while True`
    that stopped looping show as `unhealthy` in `docker ps` and as a `warn` in
    `/healthz`. **Compose does not restart a container for being unhealthy** —
    that is a Swarm behaviour — so `restart: unless-stopped` only covers a
    process that *exits*, which is the failure mode the worker was already
    handling. Closing the gap needs either an autoheal sidecar (a sixth
    container on a box shared with four other tenants, holding the Docker
    socket, which is its own risk) or an external watchdog that reads
    `/healthz`. Neither is worth adding blind. Detection first; if a wedge
    actually happens, the log from it will say which fix is the right one.

82. **`/healthz` queries the database on every request** (2026-08-09, session
    25, ADR-47). Four small queries — `SELECT 1`, the alembic revision, a plan
    count, a queue count and min. Nothing polls it on a schedule today except
    the deploy gate, so this is fine; it stops being fine the moment an uptime
    monitor is pointed at it every 10 seconds. The fix is a one-second cache on
    the report, and the trigger for doing it is "we added a monitor", not a
    date.

83. **The unhealthy-body "no ok anywhere" rule is pinned for one scenario, not
    all of them** (2026-08-09, session 25, ADR-47). `deployment.sh` greps the
    body for `status` and `ok` instead of trusting the status code, so a failing
    body containing "ok" anywhere passes the gate it should fail.
    `test_health.py` asserts this for the empty-catalog failure, which is the
    only way the probe currently goes red apart from the database being down —
    but a future component whose detail string contains "broken", "token" or
    "look" would slip through untested. The real fix is `deployment.sh`
    trusting the HTTP status, which is a change to the deploy driver and wants
    its own careful pass.

84. **A client that retries into a 429 writes one audit row per retry**
    (2026-08-09, session 26, ADR-48). `billing:quota_denied` records every
    refusal, which is what makes a support question answerable — and it means a
    caller looping against an exhausted plan writes an audit row each time. The
    analyses path is bounded (the per-IP rate limit runs *before* the quota, so
    the limiter refuses first and emits nothing); project creation and
    site-audit starts are not, because no authenticated route in this codebase
    has a throttle at all (`auth-endpoint-rate-limiting` in the backlog). The
    exposure is therefore not new — an authenticated loop can already hammer
    those routes — it now also grows a table that cannot be pruned. Not solved
    with a de-duplication window because nobody has needed one, and a window is
    the kind of state that is wrong in a way you only discover during the
    incident it was meant to help with.

85. **`billing:quota_denied` and the permission-denied event are attributed to
    an org but not always to a person** (2026-08-09, session 26). `quota.consume`
    takes `context` optionally, so a caller that omits it produces an event with
    the right organization and a NULL actor. Every current call site passes it;
    the optionality exists so `quota` stays callable from a worker or a script
    that legitimately has no user. The debt is that nothing enforces the
    distinction — a future route that forgets the argument degrades the event
    silently rather than failing to compile. A required `context` with an
    explicit `OrgContext.system()` for the caller-less case would close it.

86. **The `checker:submit` trail duplicates a demand signal that already has a
    table** (2026-08-09, session 26). `checker_submissions` records every submit
    with its triple and IP hash, and the audit event now records the same submit
    again. The overlap is deliberate — the audit row is the *cost* record and
    the submission row is the *demand* record, and they answer to different
    readers — but if the checker ever goes live at volume
    (`public-checker-go-live`), it is the anonymous surface writing the most
    rows into the append-only table, and the platform-wide
    `verify_integrity(limit=5000)` sweep would fill with it. Per-org integrity
    checks are unaffected (they filter by `org_id`, and these rows have none).
    Revisit at go-live, not before.

87. **No index on `analyses(org_id, created_at)`** (2026-08-09, session 26,
    ADR-49). The history route filters by `org_id` and `kind` and sorts by
    `created_at DESC`, and the table's only relevant index is
    `ix_analyses_status_created`. Every page is a scan plus a sort. That is
    free at production's current 57 rows and stops being free somewhere in the
    low tens of thousands — which one busy month of one busy customer reaches.
    Deliberately not fixed now: an index is a migration, and migration-bearing
    work is gated on operator item B13. **The action is to add it to whatever
    migration lands next**, not to write one for it alone.

88. **The history screen does not refresh itself** (2026-08-09, session 26). A
    run submitted from the dashboard reaches `/analyses` as `queued` and stays
    that way on screen until the reader reloads — the result page polls, this
    one does not. Acceptable because the list is a way *back* to a run rather
    than a way to watch one, and the row links to the page that does poll. It
    becomes wrong the moment this screen is the first thing a user sees after
    submitting, which is a plausible next iteration.

89. **`QUOTA_ENFORCEMENT_ENABLED` does not cover the backlink refresh path**
    (2026-08-09, session 26, found by the cross-tenant leakage suite).
    `services/quota` is the single home of the kill switch, and its docstring
    claimed that turning it off "cannot half-work, leaving one path metered and
    another not." It can. `backlink.delta` calls `billing.reserve` directly —
    it needs the *credit* half as well as the count, and it predates
    `services/quota` — so with enforcement off, analyses, site audits and
    projects stop being metered and backlink refreshes do not.

    Found the way findings like this should be found: the leakage suite's
    owner-side probe got a **429 with enforcement switched off**, which is
    impossible if the switch means what it said. Harmless today —
    `BACKLINKS_ENABLED` is off in production, so the path is unreachable — and
    the docstring now states what the switch actually covers rather than what it
    was intended to. The real repair is a `quota.reserve` wrapper that gates the
    credit path the same way, and it is small; it is not done here because it
    changes billing behaviour on a branch the operator has not merged, and the
    switch's whole purpose is to be trustworthy in an emergency.

90. **The leakage suite proves isolation for the routes that exist, not for the
    queries behind them** (2026-08-09, session 26, P7.9). Every org-scoped
    operation is probed end to end, and a new route cannot be added without
    classifying it — but the guarantee is still *behavioural*. A service
    function with a missing `org_id` filter that no route reaches today is
    invisible to this suite, and would become a leak the moment somebody wires
    it up to a route that the census then dutifully records as covered. The
    structural fix is the one #63 has always named — scoping enforced at the
    query layer rather than remembered at each call site — and it stays open.

91. **The audit CSV export is capped at 5000 rows and says so only in its own
    audit event** (2026-08-09, session 26, P7.9 §6). The export is a synchronous
    request holding a database connection, so it cannot be unbounded — but a
    caller who exports a busy year gets the newest 5000 rows and **the CSV
    itself does not say it was truncated**. The `audit:export` event records
    `truncated: true` and the matched total, so the fact is recoverable, but the
    person holding the file is the one who needs it. Two cheap improvements when
    somebody hits this: a `X-Yanki-Truncated` response header, or a trailing
    comment row. The real answer is an export *artifact* — a job that produces a
    complete file — which belongs with the reporting work in M6.

92. **`scripts/set_org_plan.py` is not in the api image** (2026-08-09, session
    26, found while verifying the production deploy). The script is the
    documented escape hatch for ADR-45 — "put an organization on any tier" — and
    `operator-expected.md` gave it as the command to run. It cannot be run where
    it is needed: the Dockerfile builds from `backend/` and the script lives at
    the repo root, so `docker compose exec api python scripts/set_org_plan.py`
    fails with `No such file or directory`. The operator file now gives SQL
    instead, which works but is a worse tool for a person under time pressure.
    Fix by moving it under `backend/scripts/` (it already imports `app.*`, so
    that is where it belongs) or by adding it to the image. **Verify the fix by
    running it inside the container, not by reading the Dockerfile** — this got
    through because nobody ran the documented command on the box.
