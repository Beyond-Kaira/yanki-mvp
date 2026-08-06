import type { VisibilityGap as VisibilityGapData } from '@/lib/insights'

interface VisibilityGapProps {
  gap: VisibilityGapData
}

// Module 2: where a competitor was named and the brand was not. "Lost" is a
// count of answers, not an estimate — every row can be traced back to the
// answers behind it (design §3.2).
export default function VisibilityGap({ gap }: VisibilityGapProps) {
  const sorted = [...gap.categories].sort((a, b) => b.lost / b.total - a.lost / a.total)

  return (
    <section className="space-y-4 rounded-lg border border-surface-border bg-white p-5 sm:p-6" aria-labelledby="gap-heading">
      <div>
        <h2 id="gap-heading" className="text-lg font-semibold text-surface-foreground">
          Visibility gap
        </h2>
        <p className="text-sm text-surface-subtle">
          Answers that named a competitor and left the brand out.
        </p>
      </div>

      <div className="rounded-lg bg-danger-soft p-4">
        <p className="text-2xl font-semibold tabular-nums text-danger-strong">
          {gap.answersLost} / {gap.total}
        </p>
        <p className="text-sm text-danger-strong">
          answers recommended another brand and never named yours
        </p>
      </div>

      <ul className="divide-y divide-surface-border overflow-hidden rounded-lg border border-surface-border">
        {sorted.map((row) => {
          const pct = row.total > 0 ? Math.round((row.lost / row.total) * 100) : 0
          return (
            <li key={row.category} className="grid grid-cols-[1fr_auto_auto] items-center gap-3 px-4 py-3">
              <div className="min-w-0">
                <p className="text-sm font-medium text-surface-foreground">{row.category}</p>
                <p className="truncate text-xs text-surface-subtle">
                  {row.competitors.length > 0 ? row.competitors.join(', ') : 'no competitor named here'}
                </p>
              </div>
              <div className="h-1.5 w-24 overflow-hidden rounded bg-surface-muted">
                <div className="h-full rounded bg-danger" style={{ width: `${pct}%` }} />
              </div>
              <span className="whitespace-nowrap text-xs tabular-nums text-surface-subtle">
                {row.lost}/{row.total}
              </span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
