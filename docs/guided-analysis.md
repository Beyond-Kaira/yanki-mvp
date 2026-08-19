# Guided AI analysis

**Status:** phase 1 — `run_mode`, profile pause after prompts (ADR-50).  
**Canvas:** `guided-analysis-flow.canvas.tsx`

## Goal

Offer a **guided, interpretable** path (KYC review → prompt edit → measure) while
keeping the existing **quick** one-click run. Same six-step pipeline; guided runs
pause before the expensive execute step.

## Run modes

| Mode | Submit | Pipeline |
|------|--------|----------|
| `quick` (default) | `POST /analyses` or `{"mode":"quick"}` | All 6 steps; `status=done` |
| `guided` | `POST /analyses` with `{"mode":"guided"}` | Steps 1–3 then `status=awaiting_review` |

## Quota (ADR-50)

- **Org billing quota** and **user stock limit** are consumed at **`POST /analyses`**
  (same as quick). The row exists and holds a slot while the user reviews.
- **Measure** (later PR) will not re-charge the monthly flow quota; it only resumes
  the same analysis id.

## API (shipped)

| Change | Notes |
|--------|--------|
| `CreateAnalysisRequest.mode` | `quick` \| `guided`, default `quick` |
| `AnalysisOut.run_mode` | Echo on thin GET |
| `status=awaiting_review` | Guided pause; KYC/prompt slices available |
| `PATCH /analyses/{id}/kyc` | Allowlisted KYC fields; regen prompts; 409 if not awaiting review |
| `PATCH /analyses/{id}/prompts` | Curate set; `source` lineage; max +3 user prompts |

Each prompt row stores:

| Field | Meaning |
|-------|---------|
| `source=generated` | Deterministic template from KYC |
| `source=edited` | User changed a generated prompt |
| `source=user` | User-added prompt |
| `locked=true` | Must appear unchanged (future: core probes) |
| `editable` | API hint: `not locked` |

## Not yet shipped

- `POST /analyses/{id}/measure`
- Guided wizard UI

See also [analysis-api-split.md](analysis-api-split.md) for read slices.
