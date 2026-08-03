# Yanki — Test Suite

*Audience: every engineer. This document is how ["done" from the MVP PRD](02-mvp.md)
is **verified**. It covers the test pyramid, the TDD workflow, fixtures, the
$0-cost rule, how to run everything, and the acceptance-criteria → test-file map.*

See also: [02-mvp.md](02-mvp.md) (scope + acceptance criteria — the "what"),
[architecture.md](architecture.md) (how it's built).

---

## 1. The golden rule: tests cost $0

**CI and the test suite NEVER call a paid API.** Every test runs against the
deterministic `MockProvider` (or a `respx`-mocked HTTP layer). This is not a
nicety — it is a hard constraint (NFR-1). Two mechanisms enforce it:

- **`DRY_RUN=1`** (the default in config) makes `providers/registry.py` hand
  back four `MockProvider`s instead of real Anthropic/OpenAI clients. The mock
  is deterministic: it mentions the company iff `sha256(prompt).digest()[0] % 2
  == 0`, and always reports `cost_usd = 0`.
- **`respx`** intercepts any real `httpx` call in the rare unit test that
  exercises a real provider adapter, so no network request ever leaves.

If a test needs a real key to pass, it is a bug in the test. Never put a real
key in a fixture, an env file, or CI.

---

## 2. The test pyramid

We keep the classic shape: many fast unit tests at the base, a middle band of
API/integration tests, and a single thin end-to-end happy path at the top.

```
        ┌───────────────────────────┐
        │   e2e (Playwright) ×1      │   happy path, gated on E2E_BASE_URL
        ├───────────────────────────┤
        │  API tests (TestClient)   │   FastAPI routes, in-process
        │  component tests (vitest) │   React components, jsdom
        ├───────────────────────────┤
        │      unit (pytest)        │   pure functions: scoring, footprint,
        │   ← the widest layer →    │   prompts, KYC parsing, mock provider
        └───────────────────────────┘
```

| Layer | Tool | Runs against | Speed | Count |
|---|---|---|---|---|
| Backend unit | pytest | pure functions, no I/O | ms | most tests |
| Backend API | pytest + FastAPI `TestClient` | in-process app, in-memory SQLite | fast | one file |
| Backend queue (portable) | pytest | in-memory SQLite (SELECT + UPDATE path) | fast | `test_queue.py` |
| Backend queue (real PG) | pytest + `TEST_DATABASE_URL` | real Postgres (skips if unset/unreachable) | medium | `test_queue_postgres.py` |
| Frontend component | vitest + testing-library | React in jsdom | fast | per component |
| Backend integration (real SearXNG) | pytest + a live instance | a self-hosted SearXNG (skips unless `SERP_TEST_BASE_URL` set) | slow | `tests/integration/` |
| End-to-end | Playwright | a running `DRY_RUN=1` stack | slow | one spec |

**Why the base is so wide:** the whole GEO engine is built from pure, sync
functions (`scoring`, `footprint`, `prompts`, plus KYC JSON parsing). Pure
functions are the cheapest possible thing to test — no DB, no network, no mocks
beyond a fake provider — so they carry the bulk of our confidence.

---

## 3. Backend testing (pytest)

### 3.1 Layout

```
backend/tests/
├── conftest.py            # shared fixtures (client, db_session, settings, make_analysis)
├── test_api.py            # POST/GET routes via TestClient (+ nullable serp object — ADR-28)
├── test_queue.py          # portable claim / stale-reaper / retry logic (SQLite)
├── test_queue_postgres.py # real-Postgres FOR UPDATE SKIP LOCKED (gated on TEST_DATABASE_URL)
├── serp/                  # SERP sources: adapter, mock, registry (ADR-28)
│   ├── test_searxng.py    # respx: the real payload shape + every failure mode
│   ├── test_mock.py       # deterministic DRY_RUN source ($0, no network)
│   └── test_registry.py   # source selection — off by default in every env
├── integration/           # gated on SERP_TEST_BASE_URL: real SearXNG (§3.4)
│   ├── test_searxng_live.py
│   └── searxng/           # a stdlib fixture engine + the settings.yml CI pins
└── pipeline/
    ├── conftest.py        # pipeline-only fixtures (settings, sample_kyc, models, db_session, seeded_analysis)
    ├── test_discovery.py
    ├── test_kyc.py
    ├── test_textfold.py   # ASCII fold: 1:1 length invariant (snippets depend on it)
    ├── test_prompts.py
    ├── test_execute.py
    ├── test_footprint.py
    ├── test_scoring.py
    ├── test_serp_visibility.py # query build, hit detect, score, run_serp (ADR-28)
    ├── test_seo_audit.py  # SEO/AI-readiness: weighted score, grade cap, 5 statuses (ADR-31)
    ├── test_robots.py     # which AI crawlers robots.txt allows; retrieval vs training
    ├── test_mock.py       # MockProvider determinism + $0 cost
    ├── test_registry.py   # DRY_RUN panel = 4 mocks named after PANEL_ENGINES
    └── test_runner.py     # full run_pipeline walk (+ SERP inside footprint — ADR-28)
```

Ownership note: `tests/conftest.py`, `test_api.py`, `test_queue.py`,
`test_queue_postgres.py` belong to the **backend-spine** agent; everything under
`tests/pipeline/` (including its own `conftest.py`) belongs to the **pipeline**
agent. The ADR-28 additions follow the same rule: the `serp` object cases in
`test_api.py` stay with **backend-spine**; `test_serp_visibility.py` and the
SERP cases in `test_runner.py` sit under `tests/pipeline/` with the **pipeline**
agent; and `tests/serp/` and `tests/integration/` are the SERP feature's own
area. The ADR-31 audit tests (`test_seo_audit.py`, `test_robots.py`) live under
`tests/pipeline/` too, so they are the **pipeline** agent's by the same rule.

### 3.2 What each layer tests

**Pure-function unit tests** (`pipeline/test_scoring.py`,
`test_footprint.py`, `test_prompts.py`, `test_textfold.py`) — no fixtures beyond
plain Python data.
Feed input, assert output. These are the red-green heart of the TDD loop.

- `scoring`: `geo_score(footprints, total)` equals `footprints / total`; and
  `total == 0` returns `0.0` (no `ZeroDivisionError`) — ADR-11.
- `footprint`: `detect(raw_text, kyc)` returns `(True, snippet)` when the
  brand/alias/domain appears (case-insensitive), `(False, None)` otherwise, and
  is fully deterministic (same input → same output). Snippet is ±60 chars.
- `prompts`: `generate_prompts(kyc, count)` returns exactly `count` specs, every
  `text` non-empty, every spec has a `category`, no duplicates.

**Provider-mocked tests** (`test_kyc.py`, `test_execute.py`) — inject a
`MockProvider` (or `respx` for the real adapter's HTTP shape). Never hit a
network.

- `kyc`: given canned model output, `generate_kyc(...)` strips ```json fences,
  parses, and validates against the `KYC` Pydantic model; `aliases` always
  includes the company name and the registrable domain name.
- `execute`: each prompt × each panel engine yields one `responses` row; the
  `llm_cache` is consulted before each provider call (a warm cache means no
  second call); `MAX_RESPONSES_PER_JOB` is never exceeded.

**Discovery test** (`test_discovery.py`) — use `respx` to serve fake HTML;
assert extracted text is non-empty for a reachable page and that an unreachable
site raises `PipelineError("could not read the site")` (a clean failure, not a
crash).

**API tests** (`test_api.py`) — FastAPI `TestClient`, in-process, no running
server:
- valid URL → `202` + `{"id": ...}`, and the row exists with `status=queued`;
- invalid/missing URL → `422`;
- `GET` unknown id → `404`;
- `GET` a known id → the full envelope with `result` always present (inner
  fields null until produced).

**Queue tests, portable** (`test_queue.py`) — the claim mechanics that both
backends share, run against in-memory SQLite so they need no services: the
oldest `queued` row is claimed first (`status→running`, `attempts` bumped,
`claimed_at` set); the SQLite plain `SELECT`+`UPDATE` fallback branch (no
`SKIP LOCKED`) still claims; a stale `running` row (`claimed_at` older than
`stale_claim_seconds`) is reclaimed while a fresh one is left alone; and a job
whose `attempts` exceed `MAX_ATTEMPTS` (3) flips to `failed` with
`error='max retries exceeded'`.

**Queue tests, real Postgres** (`test_queue_postgres.py`) — the Postgres-only
concurrency guard SQLite cannot express: `claim_next` runs its
`FOR UPDATE SKIP LOCKED` branch, and two workers polling the same instant never
double-claim (worker A holds the row lock, worker B's `SKIP LOCKED` poll finds
nothing; once A releases, B claims it exactly once). The whole module is gated
by a `pytest.mark.skipif` on `TEST_DATABASE_URL` starting with `postgresql`, so
the default `uv run pytest` stays hermetic; `make test` sets that env to the
throwaway :5433 container.

**SERP visibility tests (ADR-28)** — the whole SERP path except the live
instance, all hermetic. `serp/test_searxng.py` drives the `SearxngSource`
adapter through `respx`, feeding it payloads trimmed field-for-field from a real
2026.8 instance (including the shapes the docs omit: a null `number_of_results`
and an `unresponsive_engines` list of `[name, reason]` pairs) and keeping the
failure modes distinct — a `403`, HTML instead of JSON, a transport error and an
unconfigured base URL all raise `SerpUnavailable`, while a `200` with an empty
result list and blocked engines parses into an **unmeasurable** page, not an
empty one. `serp/test_mock.py` pins the deterministic DRY_RUN source (same
query → same page, ~half the queries rank the mock company on its own domain,
never unmeasurable — a randomly-unmeasurable mock would make CI flaky).
`serp/test_registry.py` pins source selection, chiefly that the feature is
**dark until switched on** in every environment. `pipeline/test_serp_visibility.py`
covers the brand-free query builder (the category leads; no query may name the
brand — ADR-27's invariant on the other surface), hit detection (a domain match
OR a text match, the best rank winning), scoring (`hits / measured`, and `None` —
never `0.0` — on an empty denominator), and the `run_serp` pass: unreadable
pages drop out of the denominator instead of counting as misses, an outage
records the gap and reports "not measured", and no exception it can raise (not
even an adapter bug) fails the run. New cases in `test_runner.py` prove SERP
runs **inside the footprint step** — no seventh step, `current_step`/progress
contract untouched — and stays fully NULL unless enabled; new cases in
`test_api.py` prove the nullable `serp` object serialises with its per-query
evidence and that the three-null distinction survives the wire (`serp` absent
vs. `score` null vs. `0.0`).

**SEO / AI-readiness audit tests (ADR-31)** — pure and hermetic, no network.
`pipeline/test_seo_audit.py` pins the scoring and grading: the weighted
pass-ratio counts only *evaluable* checks, so `not_measured` and `not_applicable`
are in neither the numerator nor the denominator (an unreadable input is never a
failure and never a free pass); `audit_score` returns `None` — not `0.0` — when
nothing was evaluable; and the grade is **capped by critical failures** (one
critical fail caps a would-be A/B at C, two or more force F) so a bag of minor
passes can't average a fatal problem away. `pipeline/test_robots.py` covers the
flagship AI-crawler check: it parses a `robots.txt` and reports each crawler's
access to `/`, keeping **retrieval** blocks (cost answers today → the audit fails)
apart from **training** blocks (erode presence over time → the audit only warns),
reading a 404 or empty file as "allow all" (an answer — measured) while a
transport error or a `401`/`403` is **not measured** and never guessed as blocked,
and reporting-but-never-scoring an agent whose vendor documents that it ignores
`robots.txt`. The frontend counterpart (`SeoAudit.test.tsx`, §4) proves the same
five-status distinction renders honestly.

### 3.3 SQLite for unit, Postgres for the queue

Models are written to be **SQLite-compatible** so nearly the whole suite —
including the portable queue logic in `test_queue.py` — runs against an in-memory
SQLite database with zero external services: instant, hermetic, CI-friendly. The
only tests that genuinely need Postgres semantics (`FOR UPDATE SKIP LOCKED`) live
in `test_queue_postgres.py` and use `TEST_DATABASE_URL`.

**Skip when Postgres is absent.** `test_queue_postgres.py` guards itself two
ways: a module-level `pytest.mark.skipif` skips the whole file unless
`TEST_DATABASE_URL` names a `postgresql` URL, and its `pg_sessionmaker` fixture
also tries a real connection and `pytest.skip(...)`s (rather than errors) if it
cannot reach the server. So a laptop with no Docker still gets a green
(mostly-run) suite, and `make test`/CI — which start Postgres — run them for
real.

```python
# test_queue_postgres.py sketch
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL.startswith("postgresql"),
    reason="TEST_DATABASE_URL is not a Postgres URL (set by `make test`)",
)

@pytest.fixture()
def pg_sessionmaker():
    engine = create_engine(TEST_DATABASE_URL, future=True)
    try:
        engine.connect().close()
    except Exception as exc:
        pytest.skip(f"Postgres unreachable at TEST_DATABASE_URL: {exc}")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, ...)
    Base.metadata.drop_all(engine)
    engine.dispose()
```

### 3.4 SERP integration tests against a real SearXNG (gated)

`tests/serp/` mocks the HTTP layer, which proves we parse the payload we
*believe* SearXNG sends. `tests/integration/test_searxng_live.py` proves we
parse the one it *actually* sends — the failure it exists to catch is an
upstream release moving a field, which no `respx` mock can ever see. It is a
distinct tier, not another unit test: it needs a running instance, so it is
**skipped unless `SERP_TEST_BASE_URL` is set**, keeping `make test` and the
ordinary CI pytest run hermetic. (It is still $0 — SearXNG is open-source and
self-hosted, so §1 holds; what it gives up is hermeticity, not the golden rule.)

Run it locally exactly as CI does:

```bash
.github/scripts/serp-instance.sh up
cd backend && SERP_TEST_BASE_URL=http://127.0.0.1:19099 uv run pytest tests/integration
.github/scripts/serp-instance.sh down
```

`serp-instance.sh up` boots a SearXNG container that federates **exactly one
engine** — the stdlib fixture server in
`tests/integration/searxng/fixture_engine.py`. That is the whole point. The
public engines SearXNG normally queries refuse CI runners outright — measured on
a live instance, one ordinary query came back with *all four* of `brave`,
`duckduckgo`, `startpage` and `wikipedia` suspended or CAPTCHA'd — so a test
asserting "we found results" against them would be a coin flip, and a flaky gate
is a gate people learn to ignore. Federating one deterministic fixture engine
makes the results exact **and**, more usefully, the failure modes summonable: a
query containing `__empty__` returns a healthy-but-empty page (a genuine miss),
and `__boom__` makes the engine error so SearXNG lists it under
`unresponsive_engines` (unmeasurable, never a miss). That last one is what lets
the tier assert the honesty rule — an unreadable page is dropped from the
denominator, not read as absence — against **real** SearXNG rather than against a
mock of it.

The fixture engine and the instance's `settings.yml` both live in
`tests/integration/searxng/`. `serp-instance.sh` generates SearXNG's `secret_key`
at boot (the committed `settings.yml` carries a placeholder — this repo is public
and CI scans its full history with gitleaks, so a literal key would be both a lie
and a build failure), pins the image to a known tag by default, and waits on a
real JSON search rather than `/healthz`: an instance answers `/healthz` while its
JSON format is still off, and that misconfiguration is exactly what these tests
must not mistake for a code bug.

---

## 4. Frontend testing (vitest + testing-library)

```
frontend/
├── tests/                        # vitest picks up tests/**/*.test.{ts,tsx}
│   ├── UrlForm.test.tsx          # behaviour: validation + submit
│   ├── ScoreGauge.test.tsx       # behaviour: aria-label wording + colour band
│   ├── score.test.ts             # behaviour: scoreBand boundaries
│   ├── SerpVisibility.test.tsx   # behaviour: the three SERP nulls, rendered (ADR-28)
│   ├── SeoAudit.test.tsx         # behaviour: grade headline + 5 statuses kept distinct (ADR-31)
│   ├── UrlForm.a11y.test.tsx     # axe: default + invalid-URL error state
│   ├── ScoreGauge.a11y.test.tsx  # axe: danger / primary / success bands
│   ├── StepProgress.a11y.test.tsx # axe: running (progressbar) + queued
│   ├── ResultsTable.a11y.test.tsx # axe: footprint yes/no + null snippet
│   ├── AnalysisPage.a11y.test.tsx # axe: running / failed (alert) / results
│   ├── SerpVisibility.a11y.test.tsx # axe: hit/miss/unreadable rows + not-measured
│   ├── SeoAudit.a11y.test.tsx    # axe: grade + pass/warn/fail/not_measured/not_applicable rows
│   ├── a11y.ts                   # shared axeCheck() helper (not a test file)
│   └── vitest-axe.d.ts           # Vitest-2 matcher type augmentation
├── vitest.setup.ts               # jest-dom + vitest-axe matchers, cleanup
└── e2e/happy-path.spec.ts        # Playwright
```

Vitest + `@testing-library/react` render components into **jsdom** (config in
`vitest.config.ts`, `include: ['tests/**/*.test.{ts,tsx}']`) — no browser, no
network. Five units with real logic get behaviour tests, and a parallel
**axe accessibility layer** (§4.1) asserts no violations on the same components:

- **`UrlForm`** (`UrlForm.test.tsx`) — validation: a malformed URL shows an inline
  `role="alert"` and never calls `createAnalysis`; a valid `https://…` URL calls
  `createAnalysis(url)` and disables the button while submitting. `lib/api` and
  `next/navigation` are mocked.
- **`ScoreGauge`** (`ScoreGauge.test.tsx`) — accessibility + color band: the
  `role="img"` element carries an `aria-label` that spells the score in words
  (e.g. contains `"GEO score"`, `"45 percent"`, `"9 of 20"`), and the band class
  (`text-danger` / `text-primary` / `text-success`) tracks the score.
- **`scoreBand`** (`score.test.ts`) — the score → band mapping is a pure helper;
  the tests pin its boundaries: `<30 → danger`, `30–59 → primary`, `≥60 →
  success`.
- **`SerpVisibility`** (`SerpVisibility.test.tsx`) — the three SERP nulls (ADR-28)
  rendered honestly: a measured run shows "Appeared in *h* of *q* searches" and a
  `progressbar` at the matching `aria-valuenow`; an `unavailable` run explains it
  *could not read* search results instead of drawing a `0%`; a `no_topics` run
  says the profile gave no product category; unreadable queries are kept out of
  the per-search table but counted ("*n* search could not be read"); and a hit
  with a null rank still renders ("position unknown").
- **`SeoAudit`** (`SeoAudit.test.tsx`) — the SEO / AI-readiness audit (ADR-31)
  rendered honestly: the headline is the **grade** (A–F), not the score; the five
  per-check statuses stay distinct — `pass` / `warn` / `fail` shown as verdicts,
  while `not_measured` ("we couldn't read the input") and `not_applicable`
  ("doesn't apply here") are neither collapsed together nor drawn as failures; and
  a `null` `result.seo` (a run that did not audit) renders nothing.

Anything that talks to the API is tested by mocking `lib/api.ts`, never by
hitting a backend. Fast, deterministic, offline.

### 4.1 Accessibility layer (vitest-axe + axe-core)

The P4.5 a11y acceptance ("no critical axe violations") is **automated**. Seven
`*.a11y.test.tsx` files render each component under jsdom and run
[`axe-core`](https://github.com/dequelabs/axe-core) via
[`vitest-axe`](https://github.com/chaance/vitest-axe), asserting
`expect(results).toHaveNoViolations()`. The matchers are registered in
`vitest.setup.ts` (`expect.extend(axeMatchers)`, because vitest-axe's
extend-expect entry is inert under Vitest 2), and `tests/vitest-axe.d.ts`
re-declares the matcher types against the `vitest` module's `Assertion`
interface so the assertion type-checks. All axe calls go through one shared
helper, `tests/a11y.ts`:

```ts
export function axeCheck(container: Element) {
  return axe(container, { rules: { 'color-contrast': { enabled: false } } })
}
```

Each file exercises the states that change the DOM, not just the default render:
`UrlForm` (default **and** the invalid-URL error state — `aria-invalid` +
`aria-describedby` + `role="alert"`), `ScoreGauge` (all three colour bands),
`StepProgress` (running with a progressbar, and queued), `ResultsTable`
(footprint yes/no with a null snippet), `AnalysisPage` (running, the
`role="alert"` failure card, and the results screen), `SerpVisibility` (a
measured run with hit, miss and unreadable rows, and the not-measured state), and
`SeoAudit` (a graded run with `pass`/`warn`/`fail` rows plus the `not_measured`
and `not_applicable` states). Between them they cover
**roles, accessible names, label association, landmarks, heading order,
list/table markup, `aria-*` validity, and duplicate ids**.

**Caveat — contrast is not checked here.** jsdom performs no layout or paint, so
`getComputedStyle` returns no real colours and axe's `color-contrast` rule can
only ever return "incomplete". It is therefore **explicitly disabled** in
`axeCheck` (see the comment in `tests/a11y.ts`). Colour contrast is instead
verified out-of-band as **computed WCAG ratios recorded in the brandkit / P4.5
audit** (e.g. the `success-700` / `danger-700` text-on-`*-soft` fills at
4.57:1 and 5.30:1). The future upgrade path is a real-browser
`@axe-core/playwright` pass on the running stack, where `color-contrast` *can*
run — the same reason the e2e (§5) is browser-based.

---

## 5. End-to-end (Playwright)

One spec — `e2e/happy-path.spec.ts` — proves the whole loop renders:

1. open the landing page, fill the URL field with `https://example.com`, click
   **Run analysis**;
2. wait (up to 180 s, since the pipeline runs its steps) for the `role="img"`
   gauge whose accessible name matches `/GEO score/i` to become visible;
3. assert a percentage (`%`) is rendered on the results screen.

It runs against a real, already-running stack in `DRY_RUN=1` mode (so it costs
$0 and is deterministic). It is **gated on `E2E_BASE_URL`**: the spec picks
`test` when that env var is set and `test.skip` otherwise. This keeps `make test`
fast and hermetic while letting CI (or a dev) point Playwright at a booted stack
on demand.

**Environment caveat (honest):** running the spec needs a browser binary *and*
its OS libraries — `npx playwright install-deps` (chromium's system deps)
requires **root/sudo**. In sandboxes without sudo the e2e is simply **skipped**;
it is meant to run in CI or on a workstation where those deps can be installed.
The spec is committed and ready — only the browser/deps are the gate, alongside
`E2E_BASE_URL`.

---

## 6. How to run it

```bash
make test      # backend (pytest) + frontend (vitest --run). The everyday command.
make e2e       # Playwright happy path against a running `make dev` stack on :8140
```

What `make test` does under the hood (see the `test` target in `Makefile`):

1. If `docker` is present, start a throwaway `postgres:16` container named
   `yanki-test-db`, publishing **5433→5432** (so it never collides with a dev DB
   on 5432), and wait on `pg_isready`. If `docker` is absent it prints a note and
   the real-PG tests auto-skip (§3.3).
2. `cd backend && DRY_RUN=1 TEST_DATABASE_URL=postgresql+psycopg://yanki:yanki@localhost:5433/yanki_test uv run pytest`
   — `test_queue_postgres.py` runs against that container; everything else runs on SQLite.
3. `cd frontend && npm test -- --run` — vitest, single-shot (no watch).
4. Tear down: the container is force-removed (`docker rm -f yanki-test-db`)
   whether the run passed or failed; the target exits with the combined status.

`make e2e` sets `E2E_BASE_URL=http://localhost:$${YANKI_WEB_PORT:-8140}` itself
(honoring the same `YANKI_WEB_PORT` override as `make dev`) and runs
`playwright test`, so it assumes a `make dev` stack is already up (and that
chromium + its deps are installed — see §5).

`make test` runs the same underlying pytest + vitest commands CI runs — CI just
runs them as two separate jobs (`uv run pytest`; `npm test -- --run`), each with
its own Postgres service, rather than through this Makefile wrapper — so "green on
my machine" means "green in CI" (modulo `test_queue_postgres.py`, which CI always
exercises because it always has Postgres). Neither `make test` nor that ordinary
CI run touches `tests/integration/`: it is gated on `SERP_TEST_BASE_URL`, so it
auto-skips unless you boot an instance (§3.4).

Beyond those two jobs, a separate **`SERP` workflow** (`.github/workflows/serp.yml`,
ADR-28) runs the three things CI structurally cannot, plus a scheduled drift
check:

- **`integration`** — the live-instance tier of §3.4 against a **real** SearXNG,
  pinned to a known tag: it boots the instance with `serp-instance.sh`, sets
  `SERP_TEST_BASE_URL`, and runs `pytest tests/integration`.
- **`migration`** — applies every migration on real Postgres, snapshots the
  schema, steps back one revision, and comes forward again, asserting the
  schema **round-trips exactly**. It asserts a property rather than a list of
  table names on purpose: the first version named SERP's tables and duly
  failed on the next migration for the wrong reason. A separate step checks
  the downgrade actually changed something, so a `downgrade()` that does
  nothing cannot round-trip its way to a pass.
  and re-applies (via `.github/scripts/serp_schema_check.py`). CI's ordinary
  pytest runs on SQLite and had never applied a migration at all, so a downgrade
  that cannot revert had nowhere to be caught.
- **`stack`** — one whole analysis through the `DRY_RUN` compose stack with
  `SERP_ENABLED=1` (`.github/scripts/serp_stack_check.py`), asserting the `serp`
  summary and its evidence come back out of the API. DRY_RUN selects the
  deterministic mock SERP source, so this needs no search instance.
- **`upstream`** — the same integration suite against `searxng/searxng:latest`,
  on a daily schedule (and manual dispatch) only. It is deliberately **outside
  the PR gate**: an upstream release overnight should page us, not redden an
  unrelated PR. Scheduled runs only ever execute the copy on `main`, which is
  why the job starts working once the workflow merges — and why `SERP` is in
  `notify.yml`'s `workflows:` list.

To run one slice while developing (pytest is run from `backend/`):

```bash
cd backend && uv run pytest tests/pipeline/test_scoring.py -q   # one file
cd backend && uv run pytest -k footprint                        # by name
npm test -- --run ScoreGauge                                    # one component (from frontend/)
```

---

## 7. Fixtures

Keep fixtures small, deterministic, and free. The important ones:

| Fixture | Where | What it gives you |
|---|---|---|
| `client` | `tests/conftest.py` | a FastAPI `TestClient` with `get_session` overridden to a `StaticPool` in-memory SQLite DB |
| `db_session` | `tests/conftest.py` | a SQLAlchemy session sharing that in-memory SQLite (closed per test; schema dropped with the engine) |
| `settings` | `tests/conftest.py` | a real `app.config.Settings()` (defaults, `dry_run=True`) |
| `make_analysis` | `tests/conftest.py` | a factory that inserts and returns an `Analysis` row |
| `pg_sessionmaker` | `tests/test_queue_postgres.py` | a sessionmaker on the live test Postgres (`TEST_DATABASE_URL`), fresh tables per test, or `skip` if unreachable |
| `settings` (pipeline) | `tests/pipeline/conftest.py` | a `SimpleNamespace` mirroring `Settings` (lowercase attrs: `dry_run`, `panel_engines`, `prompt_count=4`, `max_responses_per_job=60`) |
| `sample_kyc` | `tests/pipeline/conftest.py` | a valid `KYC` object (company, description, industry, aliases, products, …) |
| `models` | `tests/pipeline/conftest.py` | the spine agent's `app.db.models`, via `importorskip` |
| `db_session` (pipeline) | `tests/pipeline/conftest.py` | a `StaticPool` in-memory SQLite session (`importorskip`s `app.db`) |
| `seeded_analysis` | `tests/pipeline/conftest.py` | a `running` `Analysis` row plus three `Prompt` rows to execute against |

Discovery tests build their HTML inline and serve it via `respx` (there is no
`sample_html` fixture). Frontend tests use plain factory data and mock
`lib/api.ts` / `next/navigation` directly — no shared fixture server. The SERP
tests add no shared fixtures either: they reuse `sample_kyc` / `db_session` /
`models` and build the rest inline — a scripted `_FakeSource` that returns one
page (or raises) per query for `run_serp`, and `respx` for the adapter. The
integration tier's only "fixture" is a whole search backend, the stdlib
`fixture_engine.py` the CI instance federates (§3.4).

Because the mock provider and the templated prompt generator are deterministic,
the same inputs always produce the same outputs — tests assert exact values, not
"roughly".

---

## 8. TDD workflow (red → green)

The pipeline steps are built test-first. The loop:

1. **Red** — write a failing test named after the acceptance criterion for the
   step (§9). Run it; watch it fail for the right reason.
2. **Green** — write the smallest code that makes it pass.
3. **Refactor** — clean up with the test as your safety net.

**Test names mirror acceptance criteria** so the suite reads like the PRD. For
example, from the Scoring row:

```python
def test_geo_score_is_footprints_over_total(): ...
def test_geo_score_zero_total_does_not_divide_by_zero(): ...
```

and from Footprint:

```python
def test_footprint_true_with_matched_snippet_when_brand_present(): ...
def test_footprint_false_and_null_snippet_when_absent(): ...
def test_footprint_is_deterministic(): ...
```

Reading the test names top to bottom should tell you what the step promises. The
pure-function steps (scoring, footprint, prompts) are the easiest place to work
this way and where the discipline pays off most.

---

## 9. Acceptance criteria → test files

Every row of [02-mvp.md §8](02-mvp.md) maps to at least one test. The coverage
bar for the MVP is **"a test exists for every acceptance row"**, not a percentage
gate (§10).

| Acceptance step | Primary test file(s) | Key assertions |
|---|---|---|
| **Submit** | `tests/test_api.py` | valid URL → `202`+`id`, row is `queued`; invalid → `422` |
| **Discovery** | `tests/pipeline/test_discovery.py` | reachable → non-empty text; unreachable → `PipelineError`, no crash |
| **KYC** | `tests/pipeline/test_kyc.py` | output validates against `KYC`; company/industry/aliases populated |
| **Prompts** | `tests/pipeline/test_prompts.py` | exactly `PROMPT_COUNT`; each has non-empty `text` + `category`; no dupes |
| **Execution** | `tests/pipeline/test_execute.py` | one response per engine per prompt; cache consulted; `MAX_RESPONSES_PER_JOB` respected |
| **Footprint** | `tests/pipeline/test_footprint.py` | present → `true`+snippet; absent → `false`/null; deterministic |
| **Scoring** | `tests/pipeline/test_scoring.py` | `score == footprints/total`; `total==0` safe |
| **Results (API)** | `tests/test_api.py` | `GET` returns KYC + prompts + responses + score; `result` always present |
| **Results (UI)** | `frontend/tests/ScoreGauge.test.tsx`, `UrlForm.test.tsx`, `score.test.ts` | gauge aria-label + color band; form validation; `scoreBand` boundaries |
| **Results (UI) — a11y (P4.5)** | `frontend/tests/{UrlForm,ScoreGauge,StepProgress,ResultsTable,AnalysisPage,SerpVisibility,SeoAudit}.a11y.test.tsx` (helper `tests/a11y.ts`) | axe: no violations across each component's DOM-changing states (roles, names, labels, landmarks, aria validity); contrast checked out-of-band (§4.1) |
| **Whole-MVP happy path** | `frontend/e2e/happy-path.spec.ts` | submit → wait for gauge → a percentage renders (DRY_RUN=1); gated on `E2E_BASE_URL` |
| *(supporting)* Full pipeline walk | `tests/pipeline/test_runner.py` | `run_pipeline` reaches `done`/progress 100; prompts + `prompt_count×4` responses; `geo_score == hits/total` |
| *(supporting)* Queue reliability (NFR-3) | `tests/test_queue.py`, `test_queue_postgres.py` | portable claim / stale-reaper / `attempts>3 → failed` (SQLite); `FOR UPDATE SKIP LOCKED` no-double-claim (real PG) |
| *(supporting, ADR-28)* SERP visibility | `tests/serp/*`, `tests/pipeline/test_serp_visibility.py`, `frontend/tests/SerpVisibility.test.tsx`, + SERP cases in `test_runner.py` / `test_api.py` | queries never name the brand; hit = domain OR text; unreadable page dropped from the denominator; three distinct nulls; fail-open; off by default |
| *(supporting, ADR-28)* SERP vs. real SearXNG | `tests/integration/test_searxng_live.py` (gated on `SERP_TEST_BASE_URL`, §3.4) | we parse the payload a real instance sends; an unreadable page is never a miss |
| *(supporting, ADR-31)* SEO / AI-readiness audit | `tests/pipeline/test_seo_audit.py`, `test_robots.py`, `frontend/tests/SeoAudit.test.tsx` (+ `.a11y`) | grade capped by critical failures; five statuses, `not_measured`/`not_applicable` excluded from the score and never a failure; retrieval-vs-training crawler block; rides inside discovery, `result.seo` null when it didn't run |

---

## 10. Coverage targets (pragmatic, not dogmatic)

We do **not** gate CI on a global coverage percentage — that tends to reward
testing trivia and punish honest, hard-to-test glue. Instead:

- **Pipeline pure functions** (`scoring`, `footprint`, `prompts`, KYC parsing,
  the SERP pure functions `build_queries` / `detect` / `serp_score`, and the
  SEO-audit pure functions `audit_score` / `audit_grade` plus `robots.evaluate`):
  aim for **~100%** line + branch coverage. They are small, pure, and the core of
  the product's credibility ("show your work") — there is no excuse for a missed
  branch here.
- **Everywhere else:** the bar is **"a test exists for every acceptance-criteria
  row" (§9)**. If a row has no test, that is the gap to close — not a number on a
  dashboard.

This matches the MVP ethos: boring, minimal, junior-readable tests that
correspond one-to-one with what we promised to ship.
