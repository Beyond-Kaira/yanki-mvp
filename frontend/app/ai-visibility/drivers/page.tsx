'use client'

import AnalysisBoundSubpage from '@/components/ai-visibility/AnalysisBoundSubpage'
import {
  driversFromAnalysis,
  type ClaimBucket,
} from '@/lib/ai-visibility-data'

export default function DriversPage() {
  return (
    <AnalysisBoundSubpage title="Drivers & Gaps">
      {(analysis) => {
        const model = driversFromAnalysis(analysis)
        return (
          <>
            <p className="text-sm text-surface-subtle">
              Visibility drivers and gaps extracted from the measured run for{' '}
              <span className="font-medium text-surface-foreground">
                {model.domain}
              </span>
            </p>

            <div className="grid gap-4 lg:grid-cols-2">
              <ClaimSection
                title="Visibility drivers"
                empty="No drivers were recorded for this run."
                buckets={model.drivers}
                tone="success"
              />
              <ClaimSection
                title="Visibility gaps"
                empty="No gaps were recorded for this run."
                buckets={model.gaps}
                tone="warning"
              />
            </div>

            <section className="space-y-3" aria-labelledby="interventions-heading">
              <h2
                id="interventions-heading"
                className="text-xl font-semibold text-surface-foreground"
              >
                Recommended interventions
              </h2>
              {model.interventions.length === 0 ? (
                <p className="rounded-xl border border-dashed border-surface-border px-4 py-8 text-center text-sm text-surface-subtle">
                  No interventions for this run yet.
                </p>
              ) : (
                <ul className="space-y-3">
                  {model.interventions.map((item) => (
                    <li
                      key={item.id}
                      className="rounded-xl border border-surface-border bg-surface p-4 shadow-sm"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="flex-1 text-sm font-semibold text-surface-foreground">
                          {item.title}
                        </p>
                        {item.label ? (
                          <span className="rounded-full bg-primary-soft px-2 py-0.5 text-[11px] font-medium text-primary-strong">
                            {item.label}
                          </span>
                        ) : null}
                        {item.priority != null ? (
                          <span className="text-xs tabular-nums text-surface-subtle">
                            Priority {Math.round(item.priority * 100) / 100}
                          </span>
                        ) : null}
                      </div>
                      {item.description ? (
                        <p className="mt-2 text-sm text-surface-subtle">
                          {item.description}
                        </p>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        )
      }}
    </AnalysisBoundSubpage>
  )
}

function ClaimSection({
  title,
  empty,
  buckets,
  tone,
}: {
  title: string
  empty: string
  buckets: ClaimBucket[]
  tone: 'success' | 'warning'
}) {
  const badge =
    tone === 'success'
      ? 'bg-success-soft text-success-strong'
      : 'bg-warning-soft text-warning-strong'

  return (
    <section className="rounded-xl border border-surface-border bg-surface p-5 shadow-sm">
      <h2 className="text-lg font-semibold text-surface-foreground">{title}</h2>
      {buckets.length === 0 ? (
        <p className="mt-4 rounded-lg border border-dashed border-surface-border px-3 py-6 text-center text-sm text-surface-subtle">
          {empty}
        </p>
      ) : (
        <ul className="mt-4 space-y-4">
          {buckets.map((bucket) => (
            <li key={bucket.category}>
              <div className="mb-2 flex items-center justify-between gap-2">
                <p className="text-sm font-medium text-surface-foreground">
                  {bucket.label}
                </p>
                <span
                  className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${badge}`}
                >
                  {bucket.claims.length}
                </span>
              </div>
              <ul className="space-y-1.5">
                {bucket.claims.map((claim) => (
                  <li
                    key={claim}
                    className="rounded-lg bg-surface-muted px-3 py-2 text-sm text-surface-subtle"
                  >
                    {claim}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
