import {
  GROUP_CATEGORIES,
  INTENT_GROUPS,
  type DriverStat,
  type IntentGroup,
} from '@/lib/insights'

interface VisibilityDriversProps {
  drivers: DriverStat[]
  promptSet: string
}

const GROUP_META: Record<IntentGroup, { label: string; description: string }> =
  {
    discovery: {
      label: 'Discovery',
      description: 'Leadership and best-of questions',
    },
    comparison: {
      label: 'Comparison',
      description: 'Comparisons and alternatives',
    },
    recommendation: {
      label: 'Recommendation',
      description: 'Choice and use-case questions',
    },
  }

function percent(value: number, total: number): number {
  return total > 0 ? Math.round((value / total) * 100) : 0
}

function groupedDrivers(drivers: DriverStat[]) {
  return INTENT_GROUPS.map((group) => {
    const categories = new Set(GROUP_CATEGORIES[group])
    const rows = drivers.filter((driver) => categories.has(driver.category))
    return {
      group,
      mentioned: rows.reduce((sum, row) => sum + row.mentioned, 0),
      total: rows.reduce((sum, row) => sum + row.total, 0),
    }
  })
}

// This view intentionally groups the six low-sample prompt categories into the
// three intent families used elsewhere in the product. It makes a 1/1 category
// less likely to read as a strong standalone conclusion.
export default function VisibilityDrivers({
  drivers,
  promptSet,
}: VisibilityDriversProps) {
  const groups = groupedDrivers(drivers)
  const totalAnswers = groups.reduce((sum, group) => sum + group.total, 0)
  const totalMentions = groups.reduce((sum, group) => sum + group.mentioned, 0)
  const visibilityRate = percent(totalMentions, totalAnswers)

  return (
    <section
      className="overflow-hidden rounded-2xl border border-surface-border bg-white shadow-sm"
      aria-labelledby="drivers-heading"
    >
      <div className="border-b border-surface-border px-5 py-5 sm:px-6">
        <p className="text-xs font-medium uppercase tracking-[0.14em] text-primary">
          Question-type performance
        </p>
        <h2
          id="drivers-heading"
          className="mt-1 text-xl font-semibold text-surface-foreground"
        >
          Brand visibility by question type
        </h2>
        <p className="mt-1 max-w-2xl text-sm leading-6 text-surface-subtle">
          See which types of questions include your brand in scored answers.
        </p>
      </div>

      <div className="border-b border-surface-border bg-primary-soft/50 px-5 py-5 sm:px-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-primary-strong">
              Overall answer visibility
            </p>
            <p className="mt-1 text-3xl font-semibold tabular-nums text-surface-foreground">
              {visibilityRate}%
            </p>
            <p className="mt-1 text-xs text-surface-subtle">
              Brand appeared in {totalMentions} of {totalAnswers} scored answers
            </p>
          </div>
          <div className="min-w-[12rem] flex-1 sm:max-w-sm">
            <div className="h-3 overflow-hidden rounded-full bg-white">
              <div
                className="h-full rounded-full bg-primary"
                style={{ width: `${visibilityRate}%` }}
              />
            </div>
            <p className="mt-2 text-right text-xs text-surface-subtle">
              Based on the current run
            </p>
          </div>
        </div>
      </div>

      <div className="p-5 sm:p-6">
        <ul className="grid gap-3 lg:grid-cols-3">
          {groups.map((row) => {
            const meta = GROUP_META[row.group]
            const rate = percent(row.mentioned, row.total)
            const mentionShare = percent(row.mentioned, totalMentions)
            return (
              <li
                key={row.group}
                className="rounded-xl border border-surface-border p-4"
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
                  <span className="rounded-full bg-primary-soft px-2.5 py-1 text-sm font-semibold tabular-nums text-primary-strong">
                    {rate}%
                  </span>
                </div>
                <div
                  className="mt-4 h-2 overflow-hidden rounded-full bg-surface-muted"
                  role="progressbar"
                  aria-label={`${meta.label} visibility: ${row.mentioned} of ${row.total} answers`}
                  aria-valuenow={rate}
                  aria-valuemin={0}
                  aria-valuemax={100}
                >
                  <div
                    className="h-full rounded-full bg-primary"
                    style={{ width: `${rate}%` }}
                  />
                </div>
                <div className="mt-3 flex items-end justify-between gap-3">
                  <div>
                    <p className="text-xs text-surface-subtle">
                      Answer presence
                    </p>
                    <p className="mt-0.5 text-sm font-medium tabular-nums text-surface-foreground">
                      {row.mentioned}/{row.total}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-surface-subtle">
                      Share of mentions
                    </p>
                    <p className="mt-0.5 text-sm font-medium tabular-nums text-surface-foreground">
                      {totalMentions > 0 ? `${mentionShare}%` : '—'}
                    </p>
                  </div>
                </div>
              </li>
            )
          })}
        </ul>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-2 rounded-lg bg-surface-muted px-3 py-2.5 text-xs text-surface-subtle">
          <span>
            Percentages show brand mentions divided by scored answers in each
            intent.
          </span>
          <span className="font-mono">{promptSet}</span>
        </div>
      </div>
    </section>
  )
}
