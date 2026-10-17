# Jira — GEO worker replicas (multi-tenant parallelism)

**Epic:** Infrastructure (`yanki,epic,infra`)  
**Canvas:** `geo-worker-replicas.canvas.tsx` (Cursor canvases)  
**Out of scope:** Standalone modules sprint; fair dispatch / org FIFO policy

## Task chain

| ID | Summary | Priority |
|----|---------|----------|
| **inf-wr-1** | Capacity research & target N | Highest |
| **inf-wr-2** | Cost/benefit & replica count decision | Highest |
| **inf-wr-3** | Implement scale-out (deploy + runbook) | Highest |
| **inf-wr-4** | Staging smoke (multi-tenant parallel) | High |

Dependency: `inf-wr-1 → inf-wr-2 → inf-wr-3 → inf-wr-4`

## Import into Jira

1. **Partial import (recommended):** [jira-geo-worker-replicas-import.csv](./jira-geo-worker-replicas-import.csv)  
   - Jira **Admin → External system import → CSV** (or your project’s import flow).  
   - Map **Parent** to the existing Epic *Infrastructure* (import file uses parent key `-6` only if your project was built from `jira-backlog-import-admin.csv`; otherwise link tasks to the Epic manually after import).

2. **Full backlog sync:** rows **123–126** in [jira-backlog-import-admin.csv](./jira-backlog-import-admin.csv).

3. **Tasks only (no epic column):** last four rows in [jira-tasks-only-import.csv](./jira-tasks-only-import.csv).

**Labels:** `yanki`, `infra`, `worker-replicas`, `inf-wr-*`

## Manual create (if import unavailable)

Copy summaries and descriptions from `jira-geo-worker-replicas-import.csv` into four Tasks under Epic **Infrastructure**.
