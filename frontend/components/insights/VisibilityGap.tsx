import {
  GROUP_CATEGORIES,
  INTENT_GROUPS,
  type IntentGroup,
  type VisibilityGap as VisibilityGapData,
} from '@/lib/insights'

interface VisibilityGapProps {
  gap: VisibilityGapData
}

const GROUP_META: Record<IntentGroup, { label: string; description: string }> =
  {
    discovery: {
      label: 'Discovery',
      description: 'Market leaders and best-of questions',
    },
    comparison: {
      label: 'Comparison',
      description: 'Comparisons and alternative searches',
    },
    recommendation: {
      label: 'Recommendation',
      description: 'Recommendations and use-case questions',
    },
  }

function percent(value: number, total: number): number {
  return total > 0 ? Math.round((value / total) * 100) : 0
}

function groupedGap(gap: VisibilityGapData) {
  return INTENT_GROUPS.map((group) => {
    const categories = new Set(GROUP_CATEGORIES[group])
    const rows = gap.categories.filter((row) => categories.has(row.category))
    return {
      group,
      total: rows.reduce((sum, row) => sum + row.total, 0),
      lost: rows.reduce((sum, row) => sum + row.lost, 0),
      names: [...new Set(rows.flatMap((row) => row.competitors))],
    }
  })
}

// An answer-level metric: another detected name appeared while the measured
// brand did not. The remainder is deliberately called "other" rather than a
// win because the backend does not yet distinguish brand mentions from empty
// or no-signal answers in this aggregate.
export default function VisibilityGap({ gap }: VisibilityGapProps) {
  const gapPct = percent(gap.answersLost, gap.total)
  const other = Math.max(0, gap.total - gap.answersLost)
  const groups = groupedGap(gap)

  return (
    <section
      className="overflow-hidden rounded-2xl border border-surface-border bg-white shadow-sm"
      aria-labelledby="gap-heading"
    >
      <div className="border-b border-surface-border px-5 py-5 sm:px-6">
        <p className="text-xs font-medium uppercase tracking-[0.14em] text-danger-strong">
          Answer-level metric
        </p>
        <h2
          id="gap-heading"
          className="mt-1 text-xl font-semibold text-surface-foreground"
        >
          Answer visibility gap
        </h2>
        <p className="mt-1 max-w-2xl text-sm leading-6 text-surface-subtle">
          How often an answer surfaced another detected name while leaving your
          brand out.
        </p>
      </div>

      <div className="grid items-center gap-6 border-b border-surface-border bg-surface-muted/60 p-5 sm:p-6 md:grid-cols-[10rem_minmax(0,1fr)]">
        <div className="flex justify-center">
          <div
            className="relative h-36 w-36"
            role="img"
            aria-label={`Answer visibility gap: ${gap.answersLost} competitor-only answers out of ${gap.total}`}
          >
            <svg
              viewBox="0 0 120 120"
              className="h-full w-full -rotate-90"
              aria-hidden="true"
            >
              <circle
                cx="60"
                cy="60"
                r="46"
                fill="none"
                className="stroke-surface-border"
                strokeWidth="14"
              />
              {gap.total > 0 ? (
                <circle
                  cx="60"
                  cy="60"
                  r="46"
                  pathLength="100"
                  fill="none"
                  className="stroke-danger"
                  strokeWidth="14"
                  strokeLinecap="round"
                  strokeDasharray={`${gapPct} ${100 - gapPct}`}
                />
              ) : null}
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-3xl font-semibold tabular-nums text-surface-foreground">
                {gapPct}%
              </span>
              <span className="text-xs text-surface-subtle">gap rate</span>
            </div>
          </div>
        </div>

        <div>
          <p className="text-lg font-semibold text-surface-foreground">
            {gap.answersLost} of {gap.total} scored answers were competitor-only
          </p>
          <p className="mt-1 text-sm leading-6 text-surface-subtle">
            “Other outcome” is not automatically a win; it can also include an
            answer where no alternative name was detected.
          </p>
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            <div className="flex items-center gap-3 rounded-lg border border-danger/20 bg-danger-soft px-3 py-2.5">
              <span className="h-2.5 w-2.5 rounded-full bg-danger" />
              <span className="min-w-0 flex-1 text-sm text-danger-strong">
                Competitor-only
              </span>
              <strong className="tabular-nums text-danger-strong">
                {gap.answersLost}
              </strong>
            </div>
            <div className="flex items-center gap-3 rounded-lg border border-surface-border bg-white px-3 py-2.5">
              <span className="h-2.5 w-2.5 rounded-full bg-surface-subtle/40" />
              <span className="min-w-0 flex-1 text-sm text-surface-subtle">
                Other outcome
              </span>
              <strong className="tabular-nums text-surface-foreground">
                {other}
              </strong>
            </div>
          </div>
        </div>
      </div>

      <div className="p-5 sm:p-6">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div>
            <h3 className="text-sm font-semibold text-surface-foreground">
              Gap by question intent
            </h3>
            <p className="mt-1 text-xs text-surface-subtle">
              Six prompt categories are grouped into three easier-to-read intent
              families.
            </p>
          </div>
          <span className="rounded-full bg-surface-muted px-2.5 py-1 text-xs text-surface-subtle">
            {gap.total} scored answers
          </span>
        </div>

        <ul className="mt-4 grid gap-3 lg:grid-cols-3">
          {groups.map((row) => {
            const meta = GROUP_META[row.group]
            const pct = percent(row.lost, row.total)
            return (
              <li
                key={row.group}
                className="rounded-xl border border-surface-border bg-white p-4"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-surface-foreground">
                      {meta.label}
                    </p>
                    <p className="mt-0.5 text-xs leading-5 text-surface-subtle">
                      {meta.description}
                    </p>
                  </div>
                  <span className="text-lg font-semibold tabular-nums text-danger-strong">
                    {pct}%
                  </span>
                </div>
                <div
                  className="mt-4 h-2 overflow-hidden rounded-full bg-surface-muted"
                  role="progressbar"
                  aria-label={`${meta.label} gap: ${row.lost} of ${row.total} answers`}
                  aria-valuenow={pct}
                  aria-valuemin={0}
                  aria-valuemax={100}
                >
                  <div
                    className="h-full rounded-full bg-danger"
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <p className="mt-2 text-xs tabular-nums text-surface-subtle">
                  {row.lost}/{row.total} competitor-only answers
                </p>

                {row.names.length > 0 ? (
                  <details className="group mt-3 border-t border-surface-border pt-3">
                    <summary className="cursor-pointer list-none text-xs font-medium text-surface-subtle hover:text-surface-foreground">
                      Detected names ({row.names.length})
                      <span className="ml-1 inline-block transition-transform group-open:rotate-180">
                        ⌄
                      </span>
                    </summary>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {row.names.map((name) => (
                        <span
                          key={name}
                          className="rounded-full bg-surface-muted px-2 py-1 text-[11px] text-surface-subtle"
                        >
                          {name}
                        </span>
                      ))}
                    </div>
                  </details>
                ) : null}
              </li>
            )
          })}
        </ul>
      </div>
    </section>
  )
}
