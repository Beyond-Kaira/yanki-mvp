# GEO run schema (v2)

**Status:** adopted with ADR-51 (2026-09-07).  
**Related:** [design.md ADR-51](design.md), [analysis-api-split.md](analysis-api-split.md).

## Problem

Through ADR-34 the execute step wrote `responses.engine = "measured"` or
`"simulated"`. That field was designed for **vendor panel engines** (openai,
anthropic, …). Pipeline **mode** and **LLM identity** were conflated. The same
metadata (`model`, `measurement_mode`, `search_provider`) was duplicated on every
`responses.audit` blob and every `geo_records` row.

## Decision

Split **run metadata** (once per analysis) from **prompt records** (once per
prompt × model slug).

### `analyses.geo_run` (JSONB, nullable until step 4 completes)

```json
{
  "mode": "measured",
  "llm": {
    "provider": "openrouter",
    "model": "openai/gpt-4o-mini",
    "models": [
      "openai/gpt-4o-mini",
      "anthropic/claude-sonnet-4.5",
      "google/gemini-2.5-flash"
    ]
  },
  "search": { "provider": "tavily" },
  "schema_version": "3.0",
  "generated_at": "2026-09-07T12:00:00+00:00"
}
```

For `simulated` runs, `search` is `null`.

- **`llm.model`** — primary slug (first in `llm.models`).
- **`llm.models`** — full fan-out list from `GEO_LLM_MODELS` / `settings.geo_llm_model_list()`.

### `responses` (one row per prompt × model)

| Column | Meaning |
|--------|---------|
| `llm_provider` | LLM gateway used (`openrouter`) — renamed from `engine` |
| `model` | OpenRouter model slug — **UI group key** (not the gateway id) |
| `audit` | Record-only payload (visibility drivers/gaps, citations, …) |
| `cost_usd` | Sum of provider calls for this row (search share + audit for measured; full call for simulated) |

**Row count:** `prompts × len(geo_run.llm.models)`, capped by `MAX_RESPONSES_PER_JOB`.

### `geo_records` (columnar record twin)

One row per `responses` row. Run-level keys (`measurement_mode`, `search_provider`)
live only on `analyses.geo_run`.

## Multi-LLM fan-out

| Mode | Search | LLM calls / prompt |
|------|--------|-------------------|
| **measured** | Tavily once (shared) | N grounded answers + N audit extractions (one pair per model) |
| **simulated** | none | N full SYSTEM_PROMPT audits |

Configured via `GEO_LLM_MODELS` (comma-separated OpenRouter slugs). Default: three
models (GPT-4o mini, Claude Sonnet 4.5, Gemini 2.5 Flash).

## Read path (checker)

`engine_presence` groups by **`response.model`** slug (legacy rows fall back to
`llm_provider`). Totals sum to `total_responses`; mentioned counts sum to
`footprint_count`.

## UI surfaces

| Surface | Group key |
|---------|-----------|
| `QuestionBreakdown` chips | `response.model` slug |
| `EnginePresenceMap` | `engine_presence[].engine` (= model slug) |
| `StepProgress` execute panel | `GEO_LLM_MODELS` from generated methodology |
| Results answer header | `OpenRouter · {modelSlugLabel(slug)}` |

No nested `measured: { claude: {} }` API shape — flat `responses[]` only.

## Removed

- **`llm_cache` table** — only used by the retired four-engine `execute.py` path.
- **Legacy multi-engine panel rows** — deleted in migration 0024.
- **ADR-34 mode slugs** — backfilled to `llm_provider=openrouter` + `analyses.geo_run` in 0024.

## API follow-up

`GET /analyses/{id}/geo` may expose `geo_run` on `GeoOut` in a later slice PR.
Until then the column is persisted and consumed internally; UI defaults come from
`checker_methodology.json` → `geo_llm_models`.

## Not in scope here

- Prompt generation (`prompts.py` vs `checker_prompts.py`) — unchanged.
- Legacy `PANEL_ENGINES` registry — transitional; product path is OpenRouter fan-out.
