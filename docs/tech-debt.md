# Technical Debt — living list

*Per [session-rules.md](session-rules.md): shortcuts are fine, hidden shortcuts
are not. Every session appends here and removes what it repays. Ordered
roughly by risk.*

Last updated: 2026-08-03 (account screens, PR #13 review response, merged
against main after items #30-33 landed there: five new items — **#34**
(password reset has no endpoint, so it ships no screen), **#35**
(no terms text, so sign-up asks for no agreement), **#36** (every cold load POSTs
`/auth/refresh`, anonymous visitors included), **#37** (an account grants
nothing — no route is protected and there is no signed-in destination), **#38**
(the cross-tab refresh guard degrades on browsers without Web Locks). No
repayments this pass. Earlier — 2026-08-01 (pipeline quality part two,
`pipeline-quality-plan.md`: three new items — **#30** (`_is_html` byte-sniff
closes #28 for known binary formats, not all), **#31** (SPA bundle extraction
still welds punctuation onto real copy), **#32** (the prompt category filter is
a heuristic pending real-profile data), **#33** (grounding's 1 000-char floor is
a guess, not measured). No repayments this pass. Earlier — 2026-07-28
(discovery + KYC pass: three new items — **#27**
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
16. **The worker logs one scary-looking `UndefinedTable` error at first prod
    boot.** compose starts the worker on api `service_started`, but the api
    runs `alembic upgrade head` before uvicorn — so the worker's first poll
    can beat the migration and log a full traceback
    (`relation "analyses" does not exist`), then recover on the next poll
    (observed on the first deploy, 2026-07-10; RestartCount stayed 0). Purely
    cosmetic noise today; fix = a db-schema wait or migration-completion gate
    if it ever confuses an on-call human.
17. **`rollback.sh`'s pruned-image branch is still unproven and mutates the
    working tree.** P4.2 exercised only the images-present path (same-SHA
    rollback, clean + healthy). If the last-good image was ever pruned,
    rollback does `git checkout <sha>` + rebuild — detached HEAD, fails on a
    dirty tree, and leaves the operator's checkout moved. Surfaced by the
    session-7 pre-flight review; accepted for now (rollbacks are supervised).
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
34. **Password reset has no endpoint, so it ships no screen** (2026-08-03,
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
35. **There are no terms, so sign-up asks for no agreement** (2026-08-03,
    account screens, PR #13): the form shipped a **required** checkbox pointing
    at a `/terms` page that said, honestly, that nothing on it was binding. A
    forced consent to an unwritten document is not consent, and merging `main`
    deploys. The checkbox, `validateTermsAccepted`, `components/Checkbox.tsx`
    and the placeholder page were all removed; a test asserts the form offers no
    checkbox and no terms link, so putting one back is a deliberate act. **This
    is a legal/product blocker, not an engineering one** — the text has to be
    written before an account can be conditioned on it.
36. **Every cold load POSTs `/api/v1/auth/refresh`, anonymous visitors
    included** (2026-08-03, account screens, PR #13): `AuthProvider.restore()`
    runs on every page, and a script cannot read an httpOnly cookie, so asking
    is the only way to learn whether a session exists. The cost lands on `/` and
    `/checker` — routes that are about to go public and carry no rate limit of
    their own — as one auth POST plus a 401 per visit. The fix is a
    non-httpOnly `has_session` hint cookie set at login and cleared at logout,
    letting the client skip the call when there is obviously no session; it
    touches the backend (`auth_cookies.py`) as well as `AuthProvider`, which is
    why it is not in PR #13. **Close this before the checker goes loud.**
37. **An account grants nothing** (2026-08-03, account screens, PR #13): no
    route is protected, and there is no signed-in destination — `login/page.tsx`
    pushes to `/`, where the header shows the email. So the sign-up CTA now sits
    on every page, including `/checker`, next to the launch wedge, offering
    something that does nothing yet. Recorded as a **timing** question for the
    operator rather than a defect: the code is ready and can sit ready. Closing
    it means either the first thing worth signing in for (saved analyses,
    history) or holding the header CTA back until there is one.
38. **The cross-tab refresh guard degrades where Web Locks are missing**
    (2026-08-03, account screens, PR #13): `lib/session.ts` serialises rotation
    across tabs with `navigator.locks`, which closes the race where two tabs
    cold-loading together replay the same consumed refresh token and the backend
    revokes the whole family. Browsers without it (Safari before 15.4, Firefox
    before 96) fall back to the per-tab single-flight promise and can still hit
    that race. Deliberate: a rotation that never runs would be worse than one
    that can race, and the fallback is the behaviour every tab had before. A
    BroadcastChannel leader would cover them, at the cost of an election and
    token material crossing a channel (ADR-28, "Rejected").
