import type { DriverStat } from '@/lib/insights'

interface VisibilityDriversProps {
  drivers: DriverStat[]
  promptSet: string
}

// Module 5: which of the six question categories the brand's mentions come
// from. Deliberately narrower than "pricing / reviews / support / ..." — the
// prompt set only probes discovery, comparison and recommendation, so those
// are the only drivers this run can honestly report (design §3.5).
export default function VisibilityDrivers({ drivers, promptSet }: VisibilityDriversProps) {
  // A category with no prompts in this run has total 0, and the backend emits
  // every category it knows about whether or not the run asked one. Dividing
  // straight through would hand the comparator a NaN and leave the order up to
  // the engine's sort implementation, so an unasked category rates 0 instead.
  const rate = (driver: DriverStat) => (driver.total > 0 ? driver.mentioned / driver.total : 0)
  const sorted = [...drivers].sort((a, b) => rate(b) - rate(a))

  return (
    <section className="space-y-4 rounded-lg border border-surface-border bg-white p-5 sm:p-6" aria-labelledby="drivers-heading">
      <div>
        <h2 id="drivers-heading" className="text-lg font-semibold text-surface-foreground">
          Visibility drivers
        </h2>
        <p className="text-sm text-surface-subtle">
          Which kind of question brings up the brand — pooled across every engine.
        </p>
      </div>

      <div className="space-y-2">
        {sorted.map((driver) => {
          const pct = driver.total > 0 ? Math.round((driver.mentioned / driver.total) * 100) : 0
          return (
            <div key={driver.category} className="grid grid-cols-[7rem_minmax(0,1fr)_auto] items-center gap-3">
              <span className="truncate text-sm text-surface-subtle">{driver.category}</span>
              <div className="h-5 overflow-hidden rounded bg-surface-muted">
                <div className="h-full rounded bg-primary" style={{ width: `${pct}%` }} />
              </div>
              <span className="whitespace-nowrap text-xs tabular-nums text-surface-subtle">
                {driver.mentioned}/{driver.total} · {Math.round(driver.contribution * 100)}% of mentions
              </span>
            </div>
          )
        })}
      </div>

      <p className="text-xs text-surface-subtle">
        Based on the <span className="font-mono">{promptSet}</span> prompt set, across the {drivers.length}{' '}
        question categories it asks. A driver like pricing or reviews would need a wider question set than
        this run asked.
      </p>
    </section>
  )
}
