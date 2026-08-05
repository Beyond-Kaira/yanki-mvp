# Agent Workflows

*Audience: AI coding agents (and the humans supervising them) building Yanki in
parallel. This is the operational playbook — who may touch what, how to slice a
task, and the verify loop you run before you declare "done". For scope read
[02-mvp.md](02-mvp.md); for mechanics read the master SPEC; for session handoff
mechanics read [session-rules.md](session-rules.md).*

Read this once before your first session. Follow it every session.

---

## 1. File-ownership map

A file has exactly one owner. **Write only files you own.** Other agents edit
the rest concurrently in the same working tree — touching their files corrupts
the parallel build. When in doubt, don't write; report the blocker instead.

| Zone | Owner | Paths |
|---|---|---|
| **Backend spine** | backend-spine agent | `backend/pyproject.toml`, `backend/Dockerfile`, `backend/alembic/**`, `backend/app/{__init__,config.py,worker.py}`, `backend/app/api/**`, `backend/app/db/**`, `backend/app/jobs/**`, `backend/app/services/**`, `backend/tests/conftest.py`, `backend/tests/test_api.py`, `backend/tests/test_queue.py`, `backend/tests/test_queue_postgres.py` |
| **Pipeline + providers** | pipeline agent | `backend/app/pipeline/**`, `backend/app/providers/**`, `backend/tests/pipeline/**` (incl. its own `tests/pipeline/conftest.py`) |
| **SERP** | pipeline agent | `backend/app/serp/**` — the footprint step's source seam, so it moves with the pipeline |
| **Site Audit** | its own agent when one is running, else backend-spine | `backend/app/site_audit/**` — a self-contained crawler with its own queue and worker |
| **Backlinks** | its own agent when one is running, else backend-spine | `backend/app/backlink/**` — the M2 engine behind the `BacklinkSource` seam |
| **Frontend** | frontend agent | `frontend/**` |
| **Infra** | infra agent | `Makefile`, `deploy/**`, `scripts/**`, `.github/**`, `.gitignore`, `CONTRIBUTING.md`, `SECURITY.md`, plus README.md link fixes |
| **Docs** | doc agents | `docs/**` — **one file per agent** |
| **Generated (nobody hand-edits)** | `make gen-types` | everything under `shared/contracts/` (`openapi.json`, `checker_methodology.json`) and `frontend/lib/types.ts` |

`frontend/lib/contracts.ts` is **not** generated — it's the hand-maintained
friendly-name seam over `types.ts` (owned by the frontend agent). Edit it only
when the API contract changes; see §2 and §5.

Rule of thumb from the README still holds: a file's owner is the owner of the
directory it lives in. The table above is the authority where that's ambiguous.

---

## 2. Conflict hotspots — memorize these

These are the files most likely to cause a parallel-build collision. The rule
for each is non-negotiable.

- **`backend/pyproject.toml`** — backend-spine owns it. The dependency list is
  locked in SPEC. The pipeline agent may NOT add deps here; if the pipeline
  needs a package that isn't listed, stop and report it — do not edit the file.
- **`backend/tests/conftest.py`** — backend-spine owns it. The pipeline agent
  has its own `backend/tests/pipeline/conftest.py` and uses only that.
- **`shared/contracts/openapi.json` + `frontend/lib/types.ts`** — **generated,
  never hand-edited.** They come out of `make gen-types`. Editing them by hand
  guarantees drift and a red CI (NFR-6). See §5.
- **`frontend/lib/contracts.ts`** — the exception to the rule above: it's
  **hand-maintained**, the friendly-name seam that re-exports the generated
  `types.ts` schemas under the app's names and narrows the loosely-typed fields
  (`status`, `current_step`, `kyc`) to their locked SPEC shapes. Do edit it —
  but only when the API contract changes, and update it in lockstep with that
  change: it serializes with the contract, same as `make gen-types`. See §5.
- **`Makefile` and `deploy/**`** — infra owns them. Backend/frontend/pipeline
  agents ask infra for changes; they do not edit them.
- **`docs/*`** — one file, one agent. Don't touch another doc agent's file even
  to "fix a typo"; note it in your handoff instead.

---

## 3. How to slice a task

Take **one session-sized vertical slice** from
[implementation-plan.md](implementation-plan.md) — small enough for one focused
session, and thin enough to leave the repo runnable when you stop.

- Slice **vertically**, not by layer: e.g. "footprint step + its unit tests" or
  "ScoreGauge component + vitest", not "all backend" or "all tests".
- Stay inside your ownership zone for the whole slice. If a slice needs files in
  two zones, it's really two tasks for two agents — split it and coordinate via
  the handoff, don't cross the boundary.
- Code against the **locked contracts** in SPEC (API shapes, DB fields, env
  vars, ports, provider interface). Never invent a field or rename one.
- If you must deviate from SPEC, do it minimally and record it in your session
  log and next-session prompt.

---

## 4. The verify loop (run before you declare done)

Every agent runs this, every session, before handing off. A slice is not "done"
until it's green.

```bash
make lint        # ruff (backend) + eslint (frontend)
make typecheck   # mypy (backend) + tsc --noEmit (frontend)
make test        # pytest + vitest; DB tests auto-skip if Postgres is down
```

**For any runtime change** (API, worker, pipeline, provider, a rendered screen),
also boot the DRY_RUN stack and exercise the actual flow — tests alone don't
prove the wiring:

```bash
make dev         # db + api + worker + web, DRY_RUN=1 by default
# submit https://example.com on http://localhost:8140
# watch the 6 steps advance and a GEO score render
```

DRY_RUN=1 means the mock provider — $0 spend, deterministic. Docs-only and
config-only slices skip the stack boot but still run lint/typecheck/test where
they apply.

Definition of done for the session as a whole (SPEC): `make dev` boots,
`example.com` walks the 6 steps to a score under DRY_RUN, `make test` is green,
and docs match reality.

---

## 5. Parallelization guidance

**Safe to run concurrently** — different ownership zones with no shared contract
in flight:

- Pipeline steps + providers (pipeline agent) while the frontend agent builds
  screens against the SPEC contract.
- Infra (Makefile/compose/CI) while backend and frontend build features.
- Each doc agent on its own file.

**Must serialize** — anything that changes the API contract:

- A change to request/response shapes (`backend/app/api/schemas.py`, routes, or
  any field in the SPEC contract) forces a `make gen-types` regeneration of
  `openapi.json` + `frontend/lib/types.ts`, and — if the shape or the narrowed
  fields changed — a matching hand-edit of `frontend/lib/contracts.ts`. The
  frontend depends on those types, so **the contract change lands and types
  regenerate (and `contracts.ts` updates) before dependent frontend work
  starts.** Don't have two agents editing the API surface in the same window.
- DB schema / migration changes (backend-spine, `backend/alembic/**`) serialize
  against anything reading those columns.

When a contract change is in flight, other agents code against the SPEC's frozen
shapes and rebase onto the regenerated types once they land.

---

## 6. Handoff protocol

Every session ends with a clean handoff so no knowledge lives only in a chat
transcript. Follow [session-rules.md](session-rules.md) for the exact format;
the required artifacts are:

1. **Session log** — what you completed, what changed and why, any SPEC
   deviation, and technical debt you took on (don't hide it — track it).
2. **Next-session prompt** — a ready-to-use continuation prompt: current state,
   files that matter, remaining slice(s), current priority, constraints,
   assumptions, and acceptance criteria. The next agent should need nothing
   beyond the repo and that prompt.

If your slice changed behavior, **update the affected docs in the same session**
— documentation must never drift from implementation. If you can't (another
agent owns the doc), note it in your handoff so its owner fixes it.
