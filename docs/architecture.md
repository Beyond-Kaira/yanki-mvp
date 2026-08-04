# Yanki — Architecture

*Audience: engineers / on-call. This document describes **what session 1 actually
builds** — system + data-flow diagrams, the job lifecycle, and the deploy
topology. For the **why** behind these choices (the ADR log), see
[design.md](design.md). For **scope** see [02-mvp.md](02-mvp.md); for **how
"done" is verified** see [test-suite.md](test-suite.md).*

---

## 1. System at a glance

Four application processes over one Postgres — plus, wherever an operator has
turned SERP on (production has, ADR-29), a fifth container: an open-source
`searxng` metasearch instance the worker reads during footprint (§ outbound
calls, ADR-28). The api and the worker are the **same Docker image** (built
from `backend/Dockerfile`) started with different commands — the api serves
HTTP, the worker polls the queue. There is no message broker: the `analyses`
table *is* the queue (see §4).

```
                        ┌─────────────────────────────────────────┐
                        │                Browser                   │
                        └───────────────────┬─────────────────────┘
                                            │  HTTP (same origin)
                                            ▼
                        ┌─────────────────────────────────────────┐
   web (Next.js 15) ───▶│  web  :8140   App Router, 3 screens      │
                        │               fetch()s relative /api/... │
                        └───────────────────┬─────────────────────┘
             dev: Next.js rewrites() proxy  │  prod: host nginx path-routes
             /api/:path* + /healthz → 8141   │  /api/* + /healthz → 8141
                                            ▼
                        ┌─────────────────────────────────────────┐
   api (FastAPI, sync) │  api  :8141   POST /api/v1/analyses (202) │
                        │               GET  /api/v1/analyses/{id} │
                        │               POST /api/v1/checker (202) │
                        │               POST /api/v1/checker/leads │
                        │               GET  /healthz              │
                        └───────────────────┬─────────────────────┘
                                            │  INSERT row status='queued'
                                            ▼
                        ┌─────────────────────────────────────────┐
                        │           Postgres 16  (db)              │
                        │  analyses │ prompts │ responses │        │
                        │  llm_cache│ checker_submissions          │
                        │  serp_checks │ seo_checks                │
                        │  analyses table doubles as the job queue │
                        └───────────────────┬─────────────────────┘
                                            ▲
                                            │  claim (FOR UPDATE SKIP LOCKED),
                                            │  run 6 steps, persist, heartbeat
                        ┌───────────────────┴─────────────────────┐
   worker (sync loop)  │  worker       while True: poll + sleep    │
                        │               runs backend/app/pipeline/ │
                        │               calls providers/ + serp/   │
                        └─────────┬─────────────────────┬─────────┘
                        execute:  │                     │  footprint SERP pass —
                        DRY_RUN   │                     │  only if SERP_ENABLED=1,
                        → mock,   ▼                     ▼  reads the searxng service
                        else real/stub                     below (serp profile):
                        ┌───────────────────┐ ┌───────────────────┐
                        │ LLM providers:    │ │ searxng  :8080    │
                        │ anthropic, openai │ │ metasearch engine │
                        │ (real), gemini +  │ │ on the compose    │
                        │ perplexity (stub),│ │ network, with NO  │
                        │ mock ($0)         │ │ published port    │
                        └───────────────────┘ └─────────┬─────────┘
                                                        │ in turn queries the public
                                                        ▼ engines it is configured for:
                                                google cse · duckduckgo ·
                                                brave · startpage
```

Components (all in this repo):

| Component | Where | Port | Role |
|---|---|---|---|
| web | `frontend/` | 8140 | Next.js 15 App Router UI; submit + poll + render. |
| api | `backend/` (`app.api.main:app`) | 8141 | FastAPI, **sync**; validates + enqueues + serves status/results. |
| worker | `backend/` (`app.worker`) | — | Same image as api; polls the queue, runs the pipeline. |
| db | Postgres 16 | 5432 (dev only) | System of record **and** the job queue. |
| searxng | `deploy/` (image `searxng/searxng`, `serp` profile) | — in prod (dev: 8144, loopback) | Open-source metasearch the worker reads for the footprint SERP pass; reachable only in-network at `http://searxng:8080` (ADR-28/29). |

The api never calls an LLM and never runs a pipeline step; it only reads/writes
rows. All the slow, costly work happens in the worker.

Outbound network calls all originate in the **worker**, never the api. Discovery
fetches the submitted URL over httpx (SSRF-guarded by `net_guard` — the host must
resolve to a public address), and the SEO / AI-readiness audit that rides in that
same step (ADR-31) adds exactly one more fetch — `/robots.txt`, through
discovery's same SSRF-guarded client, so a stranger-submitted host is checked the
identical way; the execute step calls the LLM providers above;
and the footprint step's SERP pass reads a **SearXNG** instance — an open-source
metasearch engine (ADR-28) that the stack now **ships** as a profile-gated
compose service (ADR-29, §5), no longer a piece of infrastructure you stand up
by hand. Yanki's own call stays inside the compose network — the worker reads
`http://searxng:8080` — but SearXNG then makes the leg the worker never does
itself: it fans each query out to the four public web-search engines its config
keeps enabled (`google cse`, `duckduckgo`, `brave`, `startpage`) and returns
their merged results. The pass is still gated by `SERP_ENABLED` (`0` in the
shipped defaults, `1` in the production `deploy/.env`), and its base URL is
deliberately **not** run through the `net_guard` SSRF check: unlike the
stranger-submitted discovery URL it is the operator's own config, and the
intended target — a private `searxng:8080` on the compose network — is exactly
the address space that guard exists to reject.

---

## 2. Data flow — the 6-step pipeline

One analysis walks six steps in order. Each step is a plain sync function under
`backend/app/pipeline/`; the worker runs them sequentially in one job, persisting
after each step so a crash never loses completed work and partial results stay
queryable (FR-7).

```
 URL
  │
  ▼
┌───────────────┐  discovery.discover(url) -> str
│ 1. discovery  │  httpx GET (15s, UA "YankiBot/0.1"); harvest schema.org JSON-LD
│               │  (2nd fetch-free pass, leads the text, 4k cap, never follows
│               │  sameAs) + title/description/keywords/OpenGraph + visible text
│               │  (BeautifulSoup strip script/style/nav); homepage + ≤5
│               │  same-domain links, content-ful paths first (about/product/...
│               │  incl. TR hakkinda/urun/hizmet). Non-HTML + oversized responses
│               │  skipped (missing Content-Type = HTML, fail-open).
│               │  SPA fallback: if visible text <800 chars, mine ≤3 same-origin
│               │  JS bundles for prose string literals (TR-safe). ~20k cap;
│               │  unreachable/empty -> PipelineError("could not read the site")
│               │  ── THEN, in the SAME step (ADR-31): seo_audit.run_audit re-reads
│               │  this crawl + fetches ONE /robots.txt (robots.py: which AI
│               │  crawlers are allowed) and writes analyses.seo_{score,grade,
│               │  status} + seo_checks (one row/check). No new step; checker rows
│               │  have no site so they skip it. Fail-open: a defect costs the
│               │  grade, never the run.
└──────┬────────┘  ── on complete: progress = 15, current_step advances
       ▼
┌───────────────┐  kyc.generate_kyc(text, url, provider) -> KYC
│ 2. kyc        │  ONE LLM call, strict JSON (strip ```json fences, else the
│               │  outermost {…} span); ONE bounded retry if still unusable.
│               │  Pydantic KYC model. aliases always include company name +
│               │  domain-sans-TLD, plus ASCII-folded / legal-suffix-stripped
│               │  forms when they differ. persisted to analyses.kyc (jsonb)
└──────┬────────┘  ── progress = 30, then kyc.require_usable gates step 3:
       │              empty company or zero topics -> PipelineError BEFORE the
       │              paid execute fan-out (checker rows pass their category)
       ▼
┌───────────────┐  prompts.generate_prompts(kyc, count) -> list[PromptSpec]
│ 3. prompts    │  DETERMINISTIC natural-language templates, NO LLM. cycles
│               │  recommendation/makers/comparison/alternatives/best-of/use-case;
│               │  topics are specific-first (products > services > industry >
│               │  keywords) so ≥~1/3 of prompts name a real product/service.
│               │  exactly PROMPT_COUNT, non-empty, no duplicates -> prompts rows
└──────┬────────┘  ── progress = 45
       ▼
┌───────────────┐  execute: for each prompt × each panel engine
│ 4. execute    │  consult llm_cache (fresh <24h) else provider.generate()
│               │  insert responses row + llm_cache row; persist per response
│               │  stop at MAX_RESPONSES_PER_JOB (cap, don't error)
└──────┬────────┘  ── progress = 80
       ▼
┌───────────────┐  footprint.detect(raw_text, kyc) -> (bool, snippet|None)
│ 5. footprint  │  PURE, deterministic, case-insensitive search of
│               │  company/aliases/domain, \b-anchored, with diacritics folded
│               │  (textfold, 1:1 so snippet indices stay honest) and hyphen ==
│               │  space; NOT suffix-tolerant (that is roadmap §2c / step 2b).
│               │  ±60-char snippet on first hit, in its ORIGINAL spelling
│               │  updates each responses.footprint + matched_snippet
│               │  ── THEN, in the SAME step (ADR-28): serp_visibility.run_serp
│               │  searches a SearXNG instance with brand-free queries (from
│               │  prompts.topic_pool, re-checked by leaks_brand). A hit is a
│               │  domain OR text match via the same footprint.detect. Persists
│               │  serp_checks (one row/query) + analyses.serp_{score,hit_count,
│               │  query_count,status,source}. Fail-open (never raises) and OFF
│               │  by default — with no source, every serp_* column stays null.
└──────┬────────┘  ── progress = 90 (SERP adds no new step)
       ▼
┌───────────────┐  scoring.geo_score(footprints, total) -> float
│ 6. scoring    │  PURE; footprint_count / total_responses; 0.0 when total==0
│               │  writes analyses.geo_score, footprint_count, total_responses
└──────┬────────┘  ── progress = 100, status = 'done'
       ▼
 RESULTS (GET /api/v1/analyses/{id} → result{ kyc, prompts, responses, geo_score, serp, seo })
```

### Progress mapping (SPEC — set when the step COMPLETES)

| After step | `current_step` during | `progress` on complete | `status` |
|---|---|---|---|
| (enqueued) | `null` | 0 | queued |
| 1 discovery | `discovery` | 15 | running |
| 2 kyc | `kyc` | 30 | running |
| 3 prompts | `prompts` | 45 | running |
| 4 execute | `execute` | 80 | running |
| 5 footprint | `footprint` | 90 | running |
| 6 scoring | `scoring` | 100 | done |

`current_step ∈ discovery|kyc|prompts|execute|footprint|scoring|null`. The
frontend polls `GET` every 2s and renders the 6-step `StepProgress` from
`current_step` + `progress` until `status` is `done` (→ `ScoreGauge` +
`ResultsTable`) or `failed` (→ danger card with `error` + retry link).

**SERP visibility (ADR-28) runs *inside* step 5 (footprint), not as a seventh
step.** It adds no new `current_step` value, no progress checkpoint and no change
to the 6-step `StepProgress` contract — the mapping above is untouched. Its
output surfaces as a nullable `result.serp` object whose emptiness carries three
distinct meanings: `serp` **null** = never measured (the feature was off, as it
is by default, or the row predates ADR-28); a present `serp` with `score`
**null** = we searched but could not read the results; `score` **0.0** = we read
them and the company appeared in none. Unmeasurable pages — where every upstream
engine refused — are excluded from the denominator, never counted as misses.

**The SEO / AI-readiness audit (ADR-31) runs *inside* step 1 (discovery), not as
a seventh step either.** It is a second reading of the crawl discovery just paid
for plus a single `/robots.txt` fetch, so it adds no new `current_step` value, no
progress checkpoint and no change to the 6-step `StepProgress` contract — the
mapping above is untouched. Its output surfaces as a nullable `result.seo` object,
**null** on any run that did not audit (a checker submission has no site). The
headline is a **grade** (A–F), not the score: a weighted average can average a
fatal problem away, so the grade is **capped by critical failures** (one critical
fail caps at C, two or more at F) and the failing checks are the real output. Each
check carries one of five statuses — `pass` / `warn` / `fail` / `not_measured` /
`not_applicable` — and the last two are excluded from the score and mean different
things ("we could not read the input" vs. "this does not apply here"), never
collapsed into each other or shown as a failure.

### DRY_RUN / mock provider path

`DRY_RUN` defaults to **true** (safe by default). It changes exactly one thing:
which providers the worker uses. `providers/registry.py`:

- `get_panel(settings)` → **DRY_RUN=1**: four `MockProvider`s named after the
  panel engines. **DRY_RUN=0**: maps `PANEL_ENGINES` to real
  (anthropic, openai) / stub (gemini, perplexity) providers.
- `get_analysis_provider(settings)` → the single provider used for the KYC call
  (`MockProvider("mock")` when DRY_RUN).

`MockProvider` serves both prompt kinds deterministically at **$0**:

- **KYC call** (prompt contains "JSON object") → a **fixed fictional profile for
  the company `Yanki Demo Co`** (`MOCK_COMPANY`; aliases include "Yanki"). So
  **every DRY_RUN analysis, whatever URL you submit, comes back *about* Yanki
  Demo Co** — this is expected and shows up verbatim in the UI's KYC/results.
- **Execution prompts** → mentions that company iff
  `sha256(prompt).digest()[0] % 2 == 0` (≈half the answers), otherwise names
  only filler brands (Acme/Globex/Initech/…).

So the entire 6-step flow — and the whole test suite — runs offline at zero spend
and produces a stable, non-trivial score. Stub engines (gemini/perplexity) also
cost $0 and return a canned answer that *sometimes mentions nothing*, so
footprint detection sees both outcomes even outside DRY_RUN.

The SERP pass has the same `DRY_RUN` shape. When SERP is switched on **under
`DRY_RUN`**, `serp/registry.py` hands the footprint step a deterministic
`MockSerpSource` instead of `SearxngSource` — **$0, no network, no instance** — so
the SERP tests and the DRY_RUN compose stack need no SearXNG, and the score is
just hits over the queries it could actually read. With `SERP_ENABLED=0` (the
default) the registry returns *no* source and the pass is skipped entirely.

### llm_cache behavior

`execute` consults `llm_cache` before every provider call. Key =
`sha256("engine:model:prompt_text")` where `engine`/`model` come from the
provider. A row **fresh within 24h** is reused (no provider call, and the reused
`responses` row is recorded at **`cost_usd=0.0`** — a cache hit is free, it does
*not* re-bill the cached row's cost); a **stale** row is ignored and replaced
(delete + insert with a fresh timestamp). This is a **within-job / cross-job cost guard**, not a cross-account
product cache (that's out of scope — see 02-mvp.md §4). TTL is enforced at read
time, not by a sweeper.

---

## 3. Request lifecycles (submit vs. poll)

```
Submit:
  Browser ── POST /api/v1/analyses {url} ──▶ api
                                            api validates URL (http/https only)
                                            invalid → 422 (Pydantic shape / SSRF)
                                            rate-limited → 429 + Retry-After
                                            valid   → INSERT analyses (status=queued)
  Browser ◀─────────── 202 {id} ───────────  (returns immediately; no work yet)

Poll (every 2s):
  Browser ── GET /api/v1/analyses/{id} ────▶ api
                                            api reads analyses + prompts + responses
  Browser ◀── 200 {status, progress,        result{} is ALWAYS present;
              current_step, result{…}} ──    inner fields null/empty until produced
                                            unknown id → 404
```

`result` is always present so the frontend renders partial state as the pipeline
fills it in. See the locked response shape in SPEC §"API contract".

**Checker rows branch inside the same pipeline (P5.2).** A `kind='checker'`
analysis (ADR-19) walks the same six steps with two substitutions and **zero
HTTP**: step 1 builds a seed string `Brand: {brand}. Category: {category}.`
instead of crawling (the synthetic `checker://` url is never fetched), and
step 3 uses the fixed, `VERSION`-stamped 12-prompt set from
`checker_prompts.generate(kyc, lang)` (EN wired; unwired langs fall back to EN
until P5.8) instead of the templated generator. Steps 2 and 4–6, the progress
mapping, and the `StepProgress` contract are untouched. At read time (P5.3,
ADR-21) `_to_out` adds two checker-only result fields computed from stored
rows — `engine_presence` (per-engine mentioned/total from the footprint
booleans) and `competitors_appeared` (proper-noun co-mention heuristic over the
raw answers) — both `null` for MVP rows.

### Rate limiting the submit endpoint (P5.0)

`POST /api/v1/analyses` is public with real keys, so `services/rate_limit.py`
rejects abusive traffic **before** any row is created or money is spent (the
SSRF `422` check runs first, so `422`-rejected submits never count). The client
IP — first `X-Forwarded-For` entry (the host nginx edge sets it) else the socket
peer — is stored as a salted hash in the nullable `analyses.ip_hash` column;
the raw IP is never persisted. Two rolling-window guards, both returning `429`
with a `Retry-After` header:

| Env var | Default | Meaning |
|---|---|---|
| `ANALYSES_RATE_LIMIT_PER_IP_HOUR` | 5 | Max submits per client IP per rolling hour. |
| `ANALYSES_DAILY_CAP` | 100 | Global backstop: max submits across all IPs per rolling 24h. |
| `IP_HASH_SALT` | *(empty)* | Salt mixed into `sha256(salt+ip)`; blank is fine for the MVP. |

### Hardening the checker endpoint (P5.6)

`POST /api/v1/checker` reuses the same `hash_ip` / `client_ip` helpers (salted
hash into `checker_submissions.ip_hash`; raw IP never persisted). A **$0 24h
cache hit is exempt from every guard** — it still returns its analysis id and
records the submission row the email gate posts against. A **fresh** run is
guarded in this order, and a rejected submit records **nothing**:

| Env var | Default | Rejection |
|---|---|---|
| `CHECKER_ENABLED` | `0` (off) | Master kill-switch: friendly parked `503` — the public surface stays dark in every environment until the operator flips it at P5.11. |
| `CHECKER_RATE_LIMIT_PER_IP_HOUR` | 10 | `429` + `Retry-After` per client IP per rolling hour (submission rows counted). |
| `CHECKER_RATE_LIMIT_PER_BRAND_DAY` | 20 | `429`: fresh runs of one normalized `(brand, category, lang)` per rolling day — cache-served repeats don't count. |
| `CHECKER_DAILY_USD_CAP` | 5.0 | `503` "at capacity": rolling-24h sum of checker `responses.cost_usd` (always $0 under `DRY_RUN`). |

Numeric limits follow the P5.0 idiom: a value of `0` is a clean kill-switch for
that guard. See ADR-22 for the accepted residuals (XFF spoofability of the
per-IP guard; unbounded $0 cache-hit submission rows).

### Waitlist + transactional email (P5.13)

`POST /api/v1/waitlist` (the third public write path) stores a lowercased,
unique email in `waitlist_signups` (`INSERT … ON CONFLICT DO NOTHING
RETURNING` — the returned row, not rowcount, decides "new") and always
answers `202 {ok:true}` so signups can't be enumerated; per-IP 10/hour.
`services/emailer.py` posts to the Resend REST API via httpx (no SDK). It is
a no-op unless `EMAILS_ENABLED=1` **and** a key is present, and it **never
raises**: an email failure can't fail a signup or a run. Sends: on a NEW
signup, a thank-you to the joiner + an alert to `NOTIFY_EMAIL`; in the
worker, a run alert (kind, brand/url, score, link) when any analysis
reaches terminal status — the DB row is the record, the mail is the alert.
Delivery requires the operator's Resend-verified sending domain (testing
mode reaches only the account owner). ADR-25; accepted residuals in
tech-debt #24.

---

## 4. Job lifecycle — Postgres as the queue

The queue is the `analyses` table; there is no broker (NFR-4). The worker
(`backend/app/worker.py`) is a `while True` loop that sleeps `WORKER_POLL_SECONDS`
(default 2) between polls.

```
                 POST creates row
                        │
                        ▼
                  ┌───────────┐
                  │  queued   │  attempts=0, claimed_at=null, progress=0
                  └─────┬─────┘
        worker claim TX │  (one transaction, one row)
                        ▼
                  ┌───────────┐   heartbeat: worker bumps claimed_at
                  │  running  │◀─ between steps so a live job is not
                  └──┬─────┬──┘   mistaken for stale
        pipeline ok  │     │  any exception in a step
                     ▼     ▼
              ┌────────┐  ┌────────┐
              │  done  │  │ failed │  error=str(exc)[:500], partial rows kept
              └────────┘  └────────┘
                     ▲
   stale reclaim ────┘   a 'running' row whose claimed_at is older than
                         STALE_CLAIM_SECONDS is re-claimable (crashed worker).
                         attempts>3 on reclaim → failed, error='max retries exceeded'
```

### The claim query (the whole concurrency story)

One transaction selects **one** job and marks it running:

```sql
SELECT id FROM analyses
WHERE status = 'queued'
   OR (status = 'running' AND claimed_at < now() - :stale_interval)
ORDER BY created_at
LIMIT 1
FOR UPDATE SKIP LOCKED;   -- concurrent workers never grab the same row
-- then: UPDATE ... SET status='running', claimed_at=now(), attempts=attempts+1
```

- **`FOR UPDATE SKIP LOCKED`** — two workers polling at once each get a
  *different* row (or none); a job is never double-run (NFR-3). This is the only
  coordination primitive; it needs no broker and no advisory locks.
- **Stale-claim reaper via `claimed_at`** — the same `WHERE` also matches a
  `running` row whose `claimed_at` has aged past `STALE_CLAIM_SECONDS` (default
  300). A worker that crashes mid-job leaves such a row; the next poll reclaims
  it. The heartbeat (worker bumps `claimed_at` between steps) keeps a genuinely
  live long job from being reaped.
- **`attempts > 3` → failed** — each claim increments `attempts`. On the reclaim
  path, a job that has already been attempted more than 3 times is set to
  `failed` with `error='max retries exceeded'` instead of running again, so a
  poison job can't loop forever.
- **Failure containment** — any exception raised inside the pipeline sets
  `status='failed'`, `error=str(exc)` truncated to 500 chars, and leaves the rows
  written so far in place (FR-7 partial results).

State-transition summary:

| From | Trigger | To |
|---|---|---|
| queued | worker claims it | running |
| running | all 6 steps succeed | done |
| running | exception in a step | failed |
| running (claimed_at stale) | reclaimed, attempts ≤ 3 | running |
| running (claimed_at stale) | reclaimed, attempts > 3 | failed (max retries) |

---

## 5. Deploy topology

### Dev (`make dev`)

`docker compose -f deploy/docker-compose.yml up --build` (compose project name
`yanki`) brings up **db + api + worker + web** with bind-mounts for hot reload.
The **dev** api container command runs **`alembic upgrade head` before
uvicorn**, so schema migrations apply automatically on every api boot. **Prod
no longer does this**: its api serves only, and the deploy driver migrates as a
separate one-shot step *before* any container is replaced (ADR-30; see §Prod).
Dev keeps the fused form on purpose — it has no rollback to protect and CI's
e2e job relies on the stack migrating itself. **No CORS**: the frontend always
fetches relative paths, and Next.js `rewrites()` proxies `/api/:path*` and
`/healthz` to the api (`API_ORIGIN`, default `http://localhost:8141`). Postgres
publishes 5432 for local psql only.

The three published **host** ports are overridable to dodge local conflicts
(container ports stay fixed): `YANKI_WEB_PORT` (→8140), `YANKI_API_PORT` (→8141),
`YANKI_DB_PORT` (→5432). Prod has its own pair — `YANKI_PROD_WEB_PORT` (→8142)
and `YANKI_PROD_API_PORT` (→8143), loopback-bound (the prod VPS already uses
8140); the host nginx edge proxies to these binds.

```
 laptop
   http://localhost:8140  ──▶  web (Next.js dev)
                                 └─ rewrites /api/* + /healthz ─▶ api :8141
   http://localhost:8141/healthz ─────────────────────────────▶ api :8141
                                     api ─┐   worker ─┐
                                          └── db :5432 ┘  (same compose network)
```

### Prod (host nginx on `yanki.beyondkaira.com`)

Yanki runs **no edge of its own**. It deploys onto the **same VPS**
(161.97.172.146) that already serves the other beyondkaira sites (pulse-prod,
Ant Media, brier, evrak-app) — **those must never be disturbed**. The **host
nginx** vhost (`deploy/nginx/yanki.beyondkaira.com.conf`, installed under
`/etc/nginx`) terminates TLS on `yanki.beyondkaira.com` (certbot HTTP-01
webroot renewal) and **path-routes** on one origin (so still no CORS),
reaching Yanki over the stack's loopback host binds:

```
 Internet ──TLS──▶ yanki.beyondkaira.com  (host nginx, /etc/nginx vhost)
                        │                 (over 127.0.0.1 loopback binds)
                        ├─ /api/*  + /healthz ──▶ 127.0.0.1:8143 → api :8141
                        └─ everything else ──────▶ 127.0.0.1:8142 → web :8140
                                                    api + worker + db
                                                    (compose project yanki-prod)
```

- Compose project name is **`yanki-prod`**. Only web + api publish host ports,
  and those are loopback-only (`YANKI_PROD_WEB_PORT`→8142,
  `YANKI_PROD_API_PORT`→8143 — parameterized because the VPS already uses
  8140); db + worker stay on the project-internal network and Postgres is
  never published in prod.
- `make deploy` / `make rollback` follow the ams-pulse pattern: build, tag by git
  SHA, **migrate (a one-shot `alembic upgrade head`, before any running container
  is replaced)**, `compose -p yanki-prod up`, `/healthz` check, roll back to the
  last-good SHA file on failure. Both drivers run the migration as this separate
  step and the api serves only (ADR-30, issue #16): fused on boot, a
  *successful* migration made rollback impossible — the previous image's alembic
  exits 255 on a revision it has never heard of. The nginx-aware driver
  (`deploy/deployment.sh`) numbers the sequence as **7 steps**: migrate is the
  new step 4, so apply/health/record shift to 5/6/7. A bad migration now fails
  while the previous release is still serving and touches no container.
  **First exercised for real 2026-07-10 (P4.2)** — both paths ran clean on the
  shared VPS with co-tenants verified undisturbed.
- **A `searxng` service ships behind the `serp` profile (ADR-29).** The operator
  turned SERP on, so the `yanki-prod` compose file now defines a fifth container,
  `searxng` (`searxng/searxng:2026.8.1-8892414dc`, pinned like every other
  image). It is **profile-gated**: compose reads `COMPOSE_PROFILES` from the
  project-directory env file — which here *is* `deploy/.env` — so the single line
  `COMPOSE_PROFILES=serp` there is the whole opt-in and **`deployment.sh` needed
  no change**; a deployment that does not set it never creates the container.
  Turning SERP on is three lines in `deploy/.env`: `COMPOSE_PROFILES=serp`,
  `SERP_ENABLED=1`, `SERP_BASE_URL=http://searxng:8080`.
- **It publishes no host port in prod.** Only `api` and `worker` reach it, over
  the compose network at `http://searxng:8080`; its limiter is off, which is safe
  *only because* nothing is published (SearXNG's limiter 403s a bot-shaped
  client, and Yanki identifies as `YankiBot/0.1`, so the port and the limiter
  must always move together). The **dev** compose file does publish a loopback
  port (`YANKI_SEARXNG_PORT`, default 8144) for debugging. It is deliberately
  **not** a `depends_on` of api/worker — the SERP pass is fail-open, so a query
  in the seconds before the instance is ready is simply recorded as "not
  measured" (see §1) and costs the run nothing else.
- **Hard resource caps, because the VPS is shared.** `mem_limit: 512m`,
  `cpus: 0.5`, and bounded json-file logs (`max-size 10m`, `max-file 3`) fence it
  in; measured steady state is ~105–150 MiB. The box is shared with four other
  production tenants (pulse-prod, Ant Media, brier, evrak-app) and had ~3 GB
  free, so an unbounded search aggregator would be a neighbour-killer.
- **`deploy/searxng/settings.yml` is host-side, gitignored, and symlinked into
  the auto-deploy checkout** at `~/deploy/yanki-mvp/deploy/searxng/settings.yml`
  — exactly the arrangement `deploy/.env` already uses, and for the same reason:
  it carries a real `secret_key` and this repo is public with a full-history
  gitleaks scan, so only `settings.example.yml` is tracked. That file narrows
  SearXNG to the four real web-search engines and turns its JSON output on; if a
  `serp` number is unexpectedly empty, whether this file (and its symlink into
  the checkout) resolves is the first thing to check.

**One-time prerequisites** (done once by an admin — from README §Deploy):

1. On the server, `cp deploy/.env.example deploy/.env` and fill in real secrets.
   `make deploy` refuses to run without it and never auto-creates secrets.
2. ~~Point DNS~~ **done:** `yanki.beyondkaira.com → 161.97.172.146` resolves
   (verified 2026-07-10).
3. Install the nginx vhost: copy `deploy/nginx/yanki.beyondkaira.com.conf` to
   `/etc/nginx/sites-available/`, symlink into `sites-enabled/`, then
   `nginx -t` and **reload** (never restart). TLS is issued/renewed by certbot
   over HTTP-01 (webroot carve-out in the vhost's port-80 block). Full
   runbook: `deploy/MIGRATION.md`.

---

## 6. On-call quick reference

| Symptom | Where to look |
|---|---|
| Job stuck in `queued` | Is the **worker** process up? It's the same image as api, separate command. Check `make deploy-logs`. |
| Job stuck in `running` forever | Worker crashed mid-step. It self-heals: the stale-claim reaper reclaims after `STALE_CLAIM_SECONDS` (300s). |
| Job `failed` with an error | `analyses.error` holds `str(exc)` (≤500 chars). Discovery failures read "could not read the site". Partial rows remain. |
| Job `failed` at "could not identify the company / what the company does" | The step-2 usability gate (`kyc.require_usable`) stopped the run **before** any paid execute call — working as designed, not a bug. The offending profile is on the row (`analyses.kyc`): look at it. Usual causes are a site whose only content is a JS-rendered shell the SPA fallback missed, or a non-HTML homepage. |
| `max retries exceeded` | Job hit `attempts > 3` — a poison job. Inspect its `url` / `error`; don't just re-queue. |
| Unexpected LLM spend | Confirm `DRY_RUN` and `PANEL_ENGINES`; check `MAX_RESPONSES_PER_JOB` and `llm_cache` hit rate. CI/tests must stay `DRY_RUN`. |
| `result.serp` null / no SERP number | Expected unless an operator ran a SearXNG instance and set `SERP_ENABLED=1` + `SERP_BASE_URL`. SERP is off by default and **fail-open**: an instance being down leaves the `serp_*` columns null and never fails the run. A present `serp` with `score` null (not `0.0`) means the instance answered but every engine refused — see `serp_checks.unresponsive_engines`. |
| `result.seo` null / no SEO grade | Expected on a run that did not audit — a checker submission has no site, and rows predating ADR-31 never audited. On a URL run the audit rides inside discovery and always writes `analyses.seo_status` (`ok` / `no_crawl` / `error`); it is **fail-open**, so an audit defect costs the run its grade (`seo_grade` null, `seo_status='error'`) and nothing else. The failing `seo_checks` rows are the real output. |
| 404 on a valid-looking id | Unknown/never-created id. 422 instead means URL validation rejected the submit. |
| Frontend can't reach api | Dev: `rewrites()` / `API_ORIGIN`. Prod: host nginx path-routing (`/etc/nginx` vhost) + the 127.0.0.1:8142/8143 loopback binds. |

---

*Related: [design.md](design.md) (folder rationale + ADR log — the "why"),
[02-mvp.md](02-mvp.md) (scope + acceptance criteria),
[test-suite.md](test-suite.md) (how each step is tested).*
