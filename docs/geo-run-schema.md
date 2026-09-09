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
prompt).

### `analyses.geo_run` (JSONB, nullable until step 4 completes)

```json
{
  "mode": "measured",
  "llm": { "provider": "openrouter", "model": "openai/gpt-4o-mini" },
  "search": { "provider": "tavily" },
  "schema_version": "3.0",
  "generated_at": "2026-09-07T12:00:00+00:00"
}
```

For `simulated` runs, `search` is `null`.

### `responses` (one row per prompt)

| Column | Meaning |
|--------|---------|
| `llm_provider` | LLM gateway used (`openrouter`) — renamed from `engine` |
| `model` | Denormalized copy of `geo_run.llm.model` for tabular reads |
| `audit` | Record-only payload (no run-level keys) — stripped in PR-2 |

### `geo_records` (columnar record twin)

Run-level keys **removed** from columns: `model`, `measurement_mode`,
`search_provider`. They live only on `analyses.geo_run`.

## Removed

- **`llm_cache` table** — only used by the retired four-engine `execute.py` path.
- **Legacy multi-engine panel rows** — deleted in migration 0024 (retired
  ``execute.py`` path; not mappable to ADR-51).
- **ADR-34 mode slugs** — ``responses.engine = measured|simulated`` renamed in
  0023, then backfilled to ``llm_provider=openrouter`` + ``analyses.geo_run`` in
  0024 (from ``responses.audit`` / ``responses.model``).

## API (PR-4 follow-up)

`GET /analyses/{id}/geo` will expose `geo_run` on `GeoOut`. Until then the column
is persisted and returned once slice builders are updated.

## Not in scope here

- Prompt generation (`prompts.py` vs `checker_prompts.py`) — unchanged.
- `engine_presence` checker aggregate — removed or redefined in PR-4/PR-5.
