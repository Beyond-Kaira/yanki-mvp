# Yanki

**Yanki measures how visible a company is across generative-AI answers.**
You submit a company website URL; a background job crawls the site, builds a
structured company profile (KYC JSON), generates prompts, runs them across
multiple AI models, checks whether the company is mentioned, and computes a
primitive **GEO score** (mentions ÷ total responses). A second pass measures
**SERP visibility** — whether the company shows up in ordinary search results —
via a self-hosted open-source metasearch instance; it stays off by default for
anyone deploying this repo (a compose profile you opt into), but this
deployment runs it on. Long-term goal: an affordable, transparent Semrush
alternative for AI-answer rank tracking.

This README is the front door. It gets a new engineer from `git clone` to a
running local stack in about five minutes. Deeper docs live in [`docs/`](#documentation).

---

## Quickstart (about 5 minutes)

Prerequisites: **Docker + Compose v2**, **Python 3.12**, **Node 20+ (22 LTS recommended)**.
(`make setup` installs everything else — `uv`, backend/frontend deps, pre-commit.)

```bash
# 1. Clone
git clone https://github.com/aytekXR/yanki-mvp.git
cd yanki-mvp

# 2. Install the toolchain + dependencies + git hooks
make setup

# 3. Create your local env file and fill in the values
cp deploy/.env.example deploy/.env
#    Edit deploy/.env — set ANTHROPIC_API_KEY / OPENAI_API_KEY, or leave them
#    blank and set DRY_RUN=1 to run entirely on the mock provider ($0 spend).

# 4. Start the whole stack (Postgres + api + worker + web, hot reload)
make dev
```

Then open:

- **Frontend:** http://localhost:8140
- **Backend API health:** http://localhost:8141/healthz

Submit a URL on the landing page and watch the pipeline progress live.

> **Tip:** with `DRY_RUN=1` in `deploy/.env`, the pipeline uses a deterministic
> mock provider — no API keys required and zero API spend. Perfect for
> first-run and for the whole test suite.

---

## Make targets

`make` is the single control panel. Run `make help` (the default target) any
time to list everything.

| Target            | What it does                                                            |
| ----------------- | ----------------------------------------------------------------------- |
| `make help`       | List all targets (default goal).                                        |
| `make setup`      | Install `uv`, backend + frontend deps, and pre-commit hooks.            |
| `make bootstrap`  | Alias for `make setup`.                                                 |
| `make dev`        | Start the full dev stack (Postgres + api + worker + web, hot reload).   |
| `make test`       | Run backend (pytest) and frontend (vitest) test suites.                 |
| `make lint`       | Lint backend (ruff) and frontend (eslint).                             |
| `make fmt`        | Auto-format backend (ruff format) and frontend (prettier).             |
| `make typecheck`  | Type-check backend (mypy) and frontend (`tsc --noEmit`).               |
| `make migrate`    | Run Alembic migrations locally (`alembic upgrade head`).                |
| `make gen-types`  | Export `shared/contracts/openapi.json` + regenerate `frontend/lib/types.ts`. |
| `make e2e`        | Run the Playwright happy-path against a running stack (needs `make dev` up). |
| `make deploy`     | Build, deploy, migrate, and health-check on the server (auto-rollback). |
| `make rollback`   | Redeploy the last-good release SHA.                                     |
| `make deploy-logs`| Tail logs from the running server stack.                                |
| `make deploy-down`| Stop the server stack.                                                  |

---

## Port map

| Service        | Host port           | Notes                                                |
| -------------- | ------------------- | ---------------------------------------------------- |
| Frontend (web) | **8140**            | Next.js. Public via host nginx in prod.              |
| Backend (api)  | **8141**            | FastAPI. `/api/*` and `/healthz` routed here.        |
| Postgres (db)  | 5432 (**dev only**) | Never published in production; internal network only.|
| SearXNG (serp) | 8144 (**dev only**) | `serp` profile only; prod publishes no port.         |

Host ports for `make dev` are parameterized — set `YANKI_WEB_PORT`, `YANKI_API_PORT`,
or `YANKI_DB_PORT` in `deploy/.env` to dodge conflicts with something already
running (defaults 8140 / 8141 / 5432; container-internal ports are unaffected).

The optional dev `searxng` (the `serp` compose profile — `make dev` does not
start it) publishes a loopback debug port too, `YANKI_SEARXNG_PORT` (default
8144). In production nothing is published for it: only `api` and `worker` reach
it over the compose network at `http://searxng:8080`.

In production the **host nginx** vhost
(`deploy/nginx/yanki.beyondkaira.com.conf`) terminates TLS on
`yanki.beyondkaira.com` (certbot HTTP-01 webroot) and path-routes `/api/*` +
`/healthz` → api and everything else → web, over the prod stack's loopback
binds. Those binds are parameterized (`YANKI_PROD_WEB_PORT`=8142,
`YANKI_PROD_API_PORT`=8143 — 8140 is taken by another tenant on the VPS).
Same origin, so there is no CORS.

---

## Repo mini-map — "where do I put X?"

```
yanki/
├── backend/      # Python 3.12 — FastAPI api + worker + GEO engine (one image)
│   └── app/
│       ├── api/        # HTTP layer: routes + Pydantic request/response schemas
│       ├── services/   # orchestration glue between api ⇄ db ⇄ queue
│       ├── db/         # SQLAlchemy models + query helpers
│       ├── jobs/       # Postgres job queue (FOR UPDATE SKIP LOCKED)
│       ├── pipeline/   # the GEO engine (discovery → kyc → prompts → execute → footprint → scoring)
│       ├── providers/  # LLM adapters behind one Provider interface (+ mock)
│       ├── serp/       # SERP sources behind one SerpSource interface (+ mock)
│       └── worker.py   # polls the queue, runs the pipeline
├── frontend/     # Next.js 15 + TypeScript — 3 screens (submit, progress, results)
├── shared/       # cross-language contract (contracts/openapi.json)
├── deploy/       # Docker Compose + deploy/rollback scripts (ams-pulse pattern)
│   └── searxng/  # SearXNG SERP-instance config (tracked template + gitignored settings.yml)
├── scripts/      # repo-level dev utilities (gen_openapi.py, check_env.py)
├── .github/      # CI/CD workflows + PR template
└── docs/         # design, architecture, MVP scope, roadmap, brandkit, tests
```

**Rule of thumb:** a file's owner is the owner of the directory it lives in.
Anything under `deploy/`, `.github/`, `shared/contracts/`, or `backend/alembic/`
also needs the lead's review. See [`docs/design.md`](docs/design.md) for the full
ownership map.

**Do not hand-edit generated files** — `shared/contracts/openapi.json` and
`frontend/lib/types.ts` come from `make gen-types`. The app imports its types
from `frontend/lib/contracts.ts` instead — a hand-maintained seam that aliases
friendly names over the generated schemas and narrows the loosely-typed fields.

---

## Deploy

**Merging to `main` deploys itself.** Once CI is green on `main`, the `Deploy`
workflow SSHes to the VPS and ships that exact commit — build, migrate, public
health check, auto-rollback on failure. Nobody has to touch the server. The site
is live at <https://yanki.beyondkaira.com>. See
[`deploy/AUTODEPLOY.md`](deploy/AUTODEPLOY.md) for the chain, the forced-command
key that makes it safe on a shared VPS, and what is still manual (edge config
and secrets).

Deployment itself reuses the proven ams-pulse pattern — **first exercised for
real 2026-07-10** — and the same driver is still there to run by hand when you
need it (a rehearsal, a rollback, or a host with CI down):

```bash
make deploy      # build + deploy + migrate + health check (auto-rollback on failure)
make rollback    # redeploy the last-good SHA if something slips through
```

Run those from `~/repo/yanki-mvp`; auto-deploy drives a **separate** checkout at
`~/deploy/yanki-mvp` so it can never disturb your working tree.

**One-time prerequisites** (all **done** as of 2026-07-10 — see [`docs/architecture.md`](docs/architecture.md)):

1. ~~On the server, create `deploy/.env`~~ **done:** real secrets + a real
   `POSTGRES_PASSWORD` are in place. `make deploy` refuses to run without the
   file and never auto-creates secrets.
2. ~~Point DNS~~ **done:** `yanki.beyondkaira.com → 161.97.172.146` resolves
   (verified 2026-07-10). Yanki serves from the **same VPS** as the other
   beyondkaira sites (pulse-prod, Ant Media, brier) — deploys must never
   disturb them.
3. ~~Install the edge~~ **done:** the nginx vhost
   `deploy/nginx/yanki.beyondkaira.com.conf` is installed under
   `/etc/nginx/sites-available/` (enabled via symlink), validated with
   `nginx -t` and **reloaded** (never restart). TLS renews via certbot
   HTTP-01 webroot. (Originally published through the shared pulse-prod
   Caddy; migrated to host nginx per `deploy/MIGRATION.md`.)

Compose project name is `yanki-prod`. Yanki runs no edge of its own: host
nginx proxies to the stack's loopback binds — 127.0.0.1:8142 (web) /
127.0.0.1:8143 (api) by default — which are the only published host ports.

This deployment also runs the optional **SERP** pass (ADR-29). `deploy/.env`
carries three more lines — `COMPOSE_PROFILES=serp`, `SERP_ENABLED=1`, and
`SERP_BASE_URL=http://searxng:8080` — which stand up a fifth container,
`searxng`, behind the `serp` compose profile (so `deployment.sh` needs no
change). It needs a host-side `deploy/searxng/settings.yml` — gitignored (it
holds a real `secret_key`) and symlinked into the auto-deploy checkout exactly
like `deploy/.env`, created from the tracked `settings.example.yml`. Prod
publishes no port for it; only `api` and `worker` reach it over the compose
network.

---

## Documentation

| Doc                                                     | Audience              | What's in it                                             |
| ------------------------------------------------------- | --------------------- | ------------------------------------------------------- |
| [docs/design.md](docs/design.md)                        | Whole team            | Repo structure, folder rationale, ownership, ADR log.   |
| [docs/architecture.md](docs/architecture.md)            | Engineers / on-call   | System + data-flow diagrams, job lifecycle, deploy topology. |
| [docs/02-mvp.md](docs/02-mvp.md)                        | PM / QA / founders    | MVP PRD: scope, users, flow, acceptance criteria, out-of-scope. |
| [docs/roadmap.md](docs/roadmap.md)                      | Leadership / engineers| Phased path from MVP to the Semrush alternative.        |
| [docs/frontend-brandkit.md](docs/frontend-brandkit.md)  | Frontend              | Colors, type, spacing, components, voice/tone (EN + TR).|
| [docs/test-suite.md](docs/test-suite.md)                | Every engineer        | Test pyramid, TDD workflow, fixtures, coverage targets. |
| [docs/discovery-kyc-improvements.md](docs/discovery-kyc-improvements.md) | Pipeline engineers | Six steps for discovery + KYC; five shipped, 2b/6 await operator sign-off. |
| [docs/pipeline-quality-plan.md](docs/pipeline-quality-plan.md) | Pipeline engineers | MVP → product for discovery, KYC and prompts: crawl fidelity, grounded profiles, question realism. |
| [deploy/AUTODEPLOY.md](deploy/AUTODEPLOY.md)            | On-call / operators   | Merge-to-live chain, the forced-command deploy key, pruning, rotation. |

See also [CONTRIBUTING.md](CONTRIBUTING.md) for the branch/PR/commit flow and
[SECURITY.md](SECURITY.md) for the secret policy and how to report issues.
