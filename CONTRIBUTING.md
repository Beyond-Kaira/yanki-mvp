# Contributing to Yanki

Thanks for helping build Yanki. The bar is simple: **`main` is always green and
always runnable.** Keep changes small and boring.

Read [`docs/session-rules.md`](docs/session-rules.md) first — it is the
operational checklist for every session (scope, ownership, definition of done).

## Branch & PR flow

1. Branch off `main`: `git checkout -b <type>/<short-topic>`
   (e.g. `feat/score-gauge`, `fix/worker-stale-claim`).
2. Ship a **small vertical slice** — one focused change, not a giant milestone.
3. Open a PR into `main`. The template prompts you for the checklist below.
4. Merge only when CI is green.

> **Merging to `main` deploys to production.** Once CI passes on `main`, the
> `Deploy` workflow ships that commit to <https://yanki.beyondkaira.com>
> automatically — build, `alembic upgrade head`, public health check,
> auto-rollback on failure. There is no separate release step and no staging
> environment, so treat a merge as a release. Details, including how to roll
> back and how to redeploy by hand, are in
> [`deploy/AUTODEPLOY.md`](deploy/AUTODEPLOY.md).

## Slack notifications

`.github/workflows/notify.yml` posts to Slack when a PR is opened, reviewed,
closed, or merged, and when any workflow run fails. It needs one repo secret,
set once by a maintainer:

```bash
gh secret set SLACK_WEBHOOK_URL --repo Beyond-Kaira/yanki-mvp
# paste the https://hooks.slack.com/services/... URL when prompted
```

The webhook URL is **not** inlined in the workflow: this repo is public, and the
`secrets` job in `ci.yml` runs gitleaks over the full history, so a literal
`hooks.slack.com` URL would both leak the webhook and fail CI. To rotate it,
re-run the command above — no code change needed.

Note that all three triggers run the copy of the workflow on `main`, so edits to
`notify.yml` take effect once merged, not on the PR that changes them.

## Commits

- Small, self-contained commits — each one leaves the repo runnable.
- Conventional-ish subject lines: `type: summary` in the imperative mood, e.g.
  `feat: add ScoreGauge`, `fix: reclaim stale worker jobs`, `docs: update deploy`.
  Common types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.

## Before you push

Run the same checks CI runs:

```bash
make fmt        # auto-format (ruff + prettier)
make lint       # ruff + eslint
make typecheck  # mypy + tsc
make test       # backend (pytest) + frontend (vitest)
```

If you changed the API contract (any Pydantic request/response schema), also run
`make gen-types` and commit the regenerated `shared/contracts/openapi.json` and
`frontend/lib/types.ts`. CI fails on contract drift.

## Two rules that never bend

- **Docs change with the code.** Update the affected `docs/` in the same PR;
  documentation must never drift from reality.
- **No secrets in git.** Real values live in `deploy/.env` (gitignored). Only
  commit `deploy/.env.example` with placeholders. See
  [`SECURITY.md`](SECURITY.md).

## Ownership

A file's owner is the owner of the directory it lives in. Anything under
`deploy/`, `.github/`, `shared/contracts/`, or `backend/alembic/` also needs the
lead's review. See [`docs/design.md`](docs/design.md) for the full map.
