import type { SiteAuditDetail } from '@/lib/contracts'

const METRICS = [
  {
    key: 'total_errors',
    label: 'Errors',
    description: 'Critical findings that need attention.',
    tone: 'text-danger-strong',
    bar: 'bg-danger',
  },
  {
    key: 'total_warnings',
    label: 'Warnings',
    description: 'Important opportunities to review.',
    tone: 'text-warning-strong',
    bar: 'bg-warning',
  },
  {
    key: 'total_notices',
    label: 'Notices',
    description: 'Informational crawl and page signals.',
    tone: 'text-surface-subtle',
    bar: 'bg-surface-subtle',
  },
] as const

export default function IssueTotalsCard({ audit }: { audit: SiteAuditDetail }) {
  const maximum = Math.max(
    1,
    audit.total_errors,
    audit.total_warnings,
    audit.total_notices,
  )

  return (
    <article className="rounded-xl border border-surface-border bg-surface p-6 shadow-sm">
      <h2 className="text-xl font-semibold text-surface-foreground">
        Findings by severity
      </h2>
      <p className="mt-1 text-xs leading-relaxed text-surface-subtle">
        Counts from the latest completed crawl, including robots notices.
      </p>

      <div className="mt-6 space-y-6">
        {METRICS.map((metric) => {
          const value = audit[metric.key]
          return (
            <div key={metric.key}>
              <div className="flex items-end justify-between gap-4">
                <div>
                  <p className="text-sm font-medium text-surface-foreground">
                    {metric.label}
                  </p>
                  <p className="mt-0.5 text-xs text-surface-subtle">
                    {metric.description}
                  </p>
                </div>
                <p className={`text-3xl font-semibold ${metric.tone}`}>{value}</p>
              </div>
              <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-surface-muted">
                <div
                  aria-hidden="true"
                  className={`h-full rounded-full ${metric.bar}`}
                  style={{ width: `${(value / maximum) * 100}%` }}
                />
              </div>
            </div>
          )
        })}
      </div>
    </article>
  )
}
