<!-- Keep PRs small and green. See CONTRIBUTING.md. -->

## What & why

<!-- One or two sentences. Link the roadmap/implementation-plan item if there is one. -->

## Changes

-

## Checklist

- [ ] Scope stays inside `docs/02-mvp.md` (new ideas go to `roadmap.md`, not this PR).
- [ ] `make lint`, `make typecheck`, and `make test` pass locally.
- [ ] Files you changed are formatted (`cd backend && uv run ruff format <files>`) —
      CI's `format` job checks the changed files only, and it is a separate gate
      from `make lint`.
- [ ] Docs updated in the same PR (no doc drift).
- [ ] Ran `make gen-types` if the API contract changed (committed the regenerated files).
- [ ] No secrets committed — real values live in `deploy/.env` (gitignored).
