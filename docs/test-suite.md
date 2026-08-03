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
├── test_api.py            # POST/GET routes via TestClient
├── test_queue.py          # portable claim / stale-reaper / retry logic (SQLite)
├── test_queue_postgres.py # real-Postgres FOR UPDATE SKIP LOCKED (gated on TEST_DATABASE_URL)
└── pipeline/
    ├── conftest.py        # pipeline-only fixtures (settings, sample_kyc, models, db_session, seeded_analysis)
    ├── test_discovery.py
    ├── test_kyc.py
    ├── test_textfold.py   # ASCII fold: 1:1 length invariant (snippets depend on it)
    ├── test_prompts.py
    ├── test_execute.py
    ├── test_footprint.py
    ├── test_scoring.py
    ├── test_mock.py       # MockProvider determinism + $0 cost
    ├── test_registry.py   # DRY_RUN panel = 4 mocks named after PANEL_ENGINES
    └── test_runner.py     # full run_pipeline walk (all steps → score)
```

Ownership note: `tests/conftest.py`, `test_api.py`, `test_queue.py`,
`test_queue_postgres.py` belong to the **backend-spine** agent; everything under
`tests/pipeline/` (including its own `conftest.py`) belongs to the **pipeline**
agent.

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

---

## 4. Frontend testing (vitest + testing-library)

```
frontend/
├── tests/                        # vitest picks up tests/**/*.test.{ts,tsx}
│   ├── UrlForm.test.tsx          # behaviour: validation + submit
│   ├── ScoreGauge.test.tsx       # behaviour: aria-label wording + colour band
│   ├── score.test.ts             # behaviour: scoreBand boundaries
│   ├── UrlForm.a11y.test.tsx     # axe: default + invalid-URL error state
│   ├── ScoreGauge.a11y.test.tsx  # axe: danger / primary / success bands
│   ├── StepProgress.a11y.test.tsx # axe: running (progressbar) + queued
│   ├── ResultsTable.a11y.test.tsx # axe: footprint yes/no + null snippet
│   ├── AnalysisPage.a11y.test.tsx # axe: running / failed (alert) / results
│   ├── a11y.ts                   # shared axeCheck() helper (not a test file)
│   └── vitest-axe.d.ts           # Vitest-2 matcher type augmentation
├── vitest.setup.ts               # jest-dom + vitest-axe matchers, cleanup
└── e2e/happy-path.spec.ts        # Playwright
```

Vitest + `@testing-library/react` render components into **jsdom** (config in
`vitest.config.ts`, `include: ['tests/**/*.test.{ts,tsx}']`) — no browser, no
network. Three units with real logic get behaviour tests, and a parallel
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

Anything that talks to the API is tested by mocking `lib/api.ts`, never by
hitting a backend. Fast, deterministic, offline.

### 4.1 Accessibility layer (vitest-axe + axe-core)

The P4.5 a11y acceptance ("no critical axe violations") is **automated**. Five
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
(footprint yes/no with a null snippet), and `AnalysisPage` (running, the
`role="alert"` failure card, and the results screen). Between them they cover
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
exercises because it always has Postgres).

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
`lib/api.ts` / `next/navigation` directly — no shared fixture server.

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
| **Results (UI) — a11y (P4.5)** | `frontend/tests/{UrlForm,ScoreGauge,StepProgress,ResultsTable,AnalysisPage}.a11y.test.tsx` (helper `tests/a11y.ts`) | axe: no violations across each component's DOM-changing states (roles, names, labels, landmarks, aria validity); contrast checked out-of-band (§4.1) |
| **Accounts (API)** — P6.0 | `backend/tests/test_auth_api.py`, `test_auth_service.py`, `test_auth_sessions.py` | signup issues **no** session; login returns bearer + sets the refresh cookie; rotation is single-use and a replay revokes the family; `/me` needs the bearer |
| **Accounts (UI + session layer)** — P6.1 | `frontend/tests/{auth,session}.test.ts`, `{LoginPage,SignupPage,SiteHeader}.test.tsx` | one rotation per refresh **within a tab and across tabs**; a 401 refreshes once and replays carrying the new bearer; sign-out clears local state even when the request fails; the account-created-but-not-signed-in split; the header's status, not its chrome |
| **Accounts (UI) — a11y** | `frontend/tests/{LoginPage,SignupPage}.a11y.test.tsx` | axe across default, field-error and rejected-submit states; every field error is a live region and each input is described by its own; the reveal toggle keeps its name and `aria-pressed` |
| **Whole-MVP happy path** | `frontend/e2e/happy-path.spec.ts` | submit → wait for gauge → a percentage renders (DRY_RUN=1); gated on `E2E_BASE_URL` |
| *(supporting)* Full pipeline walk | `tests/pipeline/test_runner.py` | `run_pipeline` reaches `done`/progress 100; prompts + `prompt_count×4` responses; `geo_score == hits/total` |
| *(supporting)* Queue reliability (NFR-3) | `tests/test_queue.py`, `test_queue_postgres.py` | portable claim / stale-reaper / `attempts>3 → failed` (SQLite); `FOR UPDATE SKIP LOCKED` no-double-claim (real PG) |

---

## 10. Coverage targets (pragmatic, not dogmatic)

We do **not** gate CI on a global coverage percentage — that tends to reward
testing trivia and punish honest, hard-to-test glue. Instead:

- **Pipeline pure functions** (`scoring`, `footprint`, `prompts`, KYC parsing):
  aim for **~100%** line + branch coverage. They are small, pure, and the core of
  the product's credibility ("show your work") — there is no excuse for a
  missed branch here.
- **Everywhere else:** the bar is **"a test exists for every acceptance-criteria
  row" (§9)**. If a row has no test, that is the gap to close — not a number on a
  dashboard.

This matches the MVP ethos: boring, minimal, junior-readable tests that
correspond one-to-one with what we promised to ship.
