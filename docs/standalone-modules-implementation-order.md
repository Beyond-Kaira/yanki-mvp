# Standalone modules — implementation order (tracker)

**Branch:** `feat/standalone-modules-phase-a`  
**Detailed steps:** Cursor canvas `standalone-modules-action-plan.canvas.tsx`  
**Task checklist:** `standalone-modules-progress.canvas.tsx`

## Sprint sequence

Execute in this order (action-plan item numbers in parentheses):

1. **Tracker sync (4)** — progress canvas + this doc reflect repo reality.
2. ~~**rq-3 (5–8)**~~ — `module_runs` LPUSH + worker pop `queue:module` (ops below).
3. ~~**mod-4 API (9–12)**~~ — `POST/GET /api/v1/ai-visibility/runs` + `GET …/geo` (linked analysis slice).
4. **Module poll (16–17)** — `GET /api/v1/module/runs/{id}` (or equivalent) for KYC extract + future runs.
5. **mod-3 API (13–15)** — `POST/GET /api/v1/serp/runs` (+ checks). Live DataForSEO smoke when credits available.
6. **Doc cleanup (1–3)** — dedupe `standalone-modules-plan.md`, ADR-52 numbering, align progress canvas.
7. **18+** — backfill BrandContext, bundle orchestrator, frontend wizard, backlinks, site audit, rq-5.

## Status snapshot (Oct 2026)

| ID | Status | Notes |
|----|--------|--------|
| mod-0, mod-1, mod-2 | Done | Phase A |
| mod-5, mod-6 | Done | KYC profiles + worker handlers (`serp_run`, `geo_run`, `kyc_extract`) |
| mod-4 | Done | `POST/GET /api/v1/ai-visibility/runs`, `GET …/geo` |
| mod-3 | Not started | Handler only; no `/serp/runs` routes |
| rq-1 | Done | Valkey compose, `REDIS_URL`, health `redis_dispatch` |
| rq-4 | Done (analysis) | `notify_analysis_enqueued` + worker `try_pop` on `queue:analysis` |
| rq-2 | Partial | `app/jobs/redis_dispatch_queue.py` (no separate `broker.py`) |
| rq-3 | Done | `notify_module_run_enqueued` + worker `_claim_module` + `claim_module_run_by_id` |
| rq-0, rq-5 | Not started | |

## Ops — re-dispatch queued module runs (item 8)

If Postgres shows `module_runs.status = queued` but workers never pick them up (Redis was down at enqueue, or `REDIS_URL` was added later):

```bash
cd backend && uv run python ../scripts/redispatch_module_runs.py --dry-run
cd backend && uv run python ../scripts/redispatch_module_runs.py
```

KYC extract (`POST …/kyc/profiles/{id}/extract`) calls `notify_module_run_enqueued` after commit when Redis is configured. Without Redis, behavior is unchanged: worker uses `claim_next_module_run` only.

## Jira

Workstream **standalone** — keep `mod-*` and `rq-*` labels in sync when closing tasks above.
