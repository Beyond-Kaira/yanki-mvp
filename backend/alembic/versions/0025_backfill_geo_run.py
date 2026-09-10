"""Backfill geo_run and fix legacy response llm_provider values (ADR-51)

Revision ID: 0025_backfill_geo_run
Revises: 0024_geo_run_metadata
Create Date: 2026-09-09

Data-only follow-up to ``0024_geo_run_metadata``. ADR-34 stored pipeline **mode**
(``measured`` / ``simulated``) in ``responses.engine``; ADR-51 expects
``llm_provider=openrouter`` and run metadata on ``analyses.geo_run``.

Sources for backfill (``geo_records`` run-level columns are already dropped):
- ``responses.llm_provider`` — still holds the mode slug until this migration
- ``responses.model`` and ``responses.audit`` — model slug, search provider,
  schema_version, generated_at

Legacy four-engine panel rows (``anthropic``, ``openai``, …) are deleted; they
belong to the retired ``execute.py`` path and cannot be mapped to the new shape.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025_backfill_geo_run"
down_revision: str | None = "0024_geo_run_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Panel engines from the retired execute path — not GEO audit rows.
_LEGACY_PANEL_ENGINES = ("anthropic", "openai", "gemini", "perplexity", "mock")

# Expression index: makes ``migration_check.py`` detect downgrade on empty DBs and
# supports filtering analyses by run mode without scanning JSONB blobs.
_GEO_RUN_MODE_INDEX = "ix_analyses_geo_run_mode"


def upgrade() -> None:
    conn = op.get_bind()

    # 1. One geo_run blob per analysis from the first mode-slug response.
    conn.execute(
        sa.text(
            """
            UPDATE analyses AS a
            SET geo_run = jsonb_build_object(
                'mode', pick.llm_provider,
                'llm', jsonb_build_object(
                    'provider', 'openrouter',
                    'model', COALESCE(
                        NULLIF(pick.model, ''),
                        pick.audit->>'model',
                        'openai/gpt-4o-mini'
                    )
                ),
                'search', CASE
                    WHEN pick.llm_provider = 'measured' THEN jsonb_build_object(
                        'provider', COALESCE(
                            NULLIF(pick.audit->>'search_provider', ''),
                            'tavily'
                        )
                    )
                    ELSE NULL
                END,
                'schema_version', COALESCE(
                    NULLIF(pick.audit->>'schema_version', ''),
                    '3.0'
                ),
                'generated_at', COALESCE(
                    NULLIF(pick.audit->>'generated_at', ''),
                    to_char(a.updated_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"+00:00"')
                )
            )
            FROM (
                SELECT DISTINCT ON (analysis_id)
                    analysis_id,
                    llm_provider,
                    model,
                    audit
                FROM responses
                WHERE llm_provider IN ('measured', 'simulated')
                ORDER BY analysis_id, created_at
            ) AS pick
            WHERE a.id = pick.analysis_id
              AND a.geo_run IS NULL
            """
        )
    )

    # 2. Mode slug → gateway vendor id.
    conn.execute(
        sa.text(
            """
            UPDATE responses
            SET llm_provider = 'openrouter'
            WHERE llm_provider IN ('measured', 'simulated')
            """
        )
    )

    # 3. Drop retired panel rows (geo_records cascade on response delete).
    placeholders = ", ".join(f":e{i}" for i in range(len(_LEGACY_PANEL_ENGINES)))
    conn.execute(
        sa.text(f"DELETE FROM responses WHERE llm_provider IN ({placeholders})"),
        {f"e{i}": engine for i, engine in enumerate(_LEGACY_PANEL_ENGINES)},
    )

    op.create_index(
        _GEO_RUN_MODE_INDEX,
        "analyses",
        [sa.text("(geo_run->>'mode')")],
        unique=False,
        postgresql_where=sa.text("geo_run IS NOT NULL"),
    )


def downgrade() -> None:
    conn = op.get_bind()

    op.drop_index(_GEO_RUN_MODE_INDEX, table_name="analyses")

    # Restore mode slugs on rows this migration rewrote (openrouter + geo_run set).
    conn.execute(
        sa.text(
            """
            UPDATE responses AS r
            SET llm_provider = a.geo_run->>'mode'
            FROM analyses AS a
            WHERE r.analysis_id = a.id
              AND a.geo_run IS NOT NULL
              AND r.llm_provider = 'openrouter'
              AND a.geo_run->>'mode' IN ('measured', 'simulated')
            """
        )
    )

    conn.execute(sa.text("UPDATE analyses SET geo_run = NULL WHERE geo_run IS NOT NULL"))

    # Deleted panel-engine rows are not restored.
