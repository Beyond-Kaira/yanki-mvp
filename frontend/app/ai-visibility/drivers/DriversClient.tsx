'use client'

import AnalysisBoundSubpage from '@/components/ai-visibility/AnalysisBoundSubpage'
import { driversFromAnalysis, type ClaimBucket } from '@/lib/ai-visibility-data'
import VisibilityDrivers from '@/components/insights/VisibilityDrivers'
import VisibilityGap from '@/components/insights/VisibilityGap'

export default function DriversPage() {
  return (
    <AnalysisBoundSubpage title="Drivers & Gaps">
      {(analysis) => {
        const model = driversFromAnalysis(analysis)
        const insights = analysis.result.insights
        return (
          <div className="space-y-8">
            <section className="rounded-2xl border border-primary/15 bg-gradient-to-br from-primary-soft/70 via-white to-white px-5 py-5 shadow-sm sm:px-6">
              <p className="text-xs font-medium uppercase tracking-[0.14em] text-primary">
                Visibility performance
              </p>
              <div className="mt-2 flex flex-wrap items-end justify-between gap-4">
                <div>
                  <h2 className="text-2xl font-semibold tracking-tight text-surface-foreground">
                    Where {model.domain} appears — and where it does not
                  </h2>
                  <p className="mt-2 max-w-3xl text-sm leading-6 text-surface-subtle">
                    Answer performance is shown separately from generated search
                    and content diagnostics, so the two signals are not mistaken
                    for the same metric.
                  </p>
                </div>
                {insights ? (
                  <span className="rounded-full border border-primary/20 bg-white px-3 py-1.5 text-xs font-medium text-primary-strong shadow-sm">
                    {insights.scoredAnswers} scored answers
                  </span>
                ) : null}
              </div>
            </section>

            {insights ? (
              <section
                className="space-y-4"
                aria-labelledby="answer-performance-heading"
              >
                <div>
                  <p className="text-xs font-medium uppercase tracking-[0.14em] text-surface-subtle">
                    Measured answer performance
                  </p>
                  <h2
                    id="answer-performance-heading"
                    className="mt-1 text-xl font-semibold text-surface-foreground"
                  >
                    Visibility across scored answers
                  </h2>
                </div>
                <div className="grid gap-5">
                  <VisibilityGap gap={insights.gap} />
                  <VisibilityDrivers
                    drivers={insights.drivers}
                    promptSet={insights.promptSet}
                  />
                </div>
              </section>
            ) : null}

            <section
              className="space-y-4"
              aria-labelledby="diagnostics-heading"
            >
              <div className="flex flex-wrap items-end justify-between gap-3 border-b border-surface-border pb-4">
                <div>
                  <p className="text-xs font-medium uppercase tracking-[0.14em] text-warning-strong">
                    Generated diagnostics
                  </p>
                  <h2
                    id="diagnostics-heading"
                    className="mt-1 text-xl font-semibold text-surface-foreground"
                  >
                    Search & content diagnostics
                  </h2>
                  <p className="mt-1 max-w-3xl text-sm leading-6 text-surface-subtle">
                    Evidence-derived strengths and risks from scored prompts.
                    These are diagnostic observations, not additional
                    lost-answer counts.
                  </p>
                </div>
                <span className="rounded-full bg-warning-soft px-3 py-1.5 text-xs font-medium text-warning-strong">
                  Review with evidence
                </span>
              </div>

              <div className="grid items-start gap-5 lg:grid-cols-2">
                <ClaimSection
                  title="Visibility strengths"
                  description="Signals that helped the brand appear or supported its position."
                  empty="No visibility strengths were recorded for this run."
                  buckets={model.drivers}
                  tone="success"
                />
                <ClaimSection
                  title="Search & content risks"
                  description="Discoverability, ranking and content issues detected in the run."
                  empty="No search or content risks were recorded for this run."
                  buckets={model.gaps}
                  tone="warning"
                />
              </div>
            </section>

            <section
              className="overflow-hidden rounded-2xl border border-surface-border bg-white shadow-sm"
              aria-labelledby="interventions-heading"
            >
              <div className="border-b border-surface-border px-5 py-5 sm:px-6">
                <p className="text-xs font-medium uppercase tracking-[0.14em] text-primary">
                  Next actions
                </p>
                <h2
                  id="interventions-heading"
                  className="mt-1 text-xl font-semibold text-surface-foreground"
                >
                  Recommended interventions
                </h2>
                <p className="mt-1 text-sm text-surface-subtle">
                  Suggested actions generated from the measured run.
                </p>
              </div>
              <div className="p-5 sm:p-6">
                {model.interventions.length === 0 ? (
                  <p className="rounded-xl border border-dashed border-surface-border px-4 py-8 text-center text-sm text-surface-subtle">
                    No interventions for this run yet.
                  </p>
                ) : (
                  <ul className="grid gap-3 lg:grid-cols-2">
                    {model.interventions.map((item) => (
                      <li
                        key={item.id}
                        className="rounded-xl border border-surface-border bg-surface-muted/50 p-4"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="min-w-0 flex-1 text-sm font-semibold text-surface-foreground">
                            {item.title}
                          </p>
                          {item.label ? (
                            <span className="rounded-full bg-primary-soft px-2 py-0.5 text-[11px] font-medium text-primary-strong">
                              {item.label}
                            </span>
                          ) : null}
                          {item.priority != null ? (
                            <span className="rounded-full bg-white px-2 py-0.5 text-[11px] tabular-nums text-surface-subtle">
                              Priority {Math.round(item.priority * 100) / 100}
                            </span>
                          ) : null}
                        </div>
                        {item.description ? (
                          <p className="mt-2 text-sm leading-6 text-surface-subtle">
                            {item.description}
                          </p>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </section>
          </div>
        )
      }}
    </AnalysisBoundSubpage>
  )
}

function ClaimSection({
  title,
  description,
  empty,
  buckets,
  tone,
}: {
  title: string
  description: string
  empty: string
  buckets: ClaimBucket[]
  tone: 'success' | 'warning'
}) {
  const accent =
    tone === 'success'
      ? 'bg-success-soft text-success-strong'
      : 'bg-warning-soft text-warning-strong'
  const dot = tone === 'success' ? 'bg-success' : 'bg-warning'
  const totalClaims = buckets.reduce(
    (sum, bucket) => sum + bucket.claims.length,
    0,
  )

  return (
    <section className="overflow-hidden rounded-2xl border border-surface-border bg-white shadow-sm">
      <div className="border-b border-surface-border px-5 py-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-lg font-semibold text-surface-foreground">
              {title}
            </h3>
            <p className="mt-1 text-sm leading-6 text-surface-subtle">
              {description}
            </p>
          </div>
          <span
            className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${accent}`}
          >
            {totalClaims}
          </span>
        </div>
      </div>

      <div className="p-3">
        {buckets.length === 0 ? (
          <p className="rounded-xl border border-dashed border-surface-border px-3 py-8 text-center text-sm text-surface-subtle">
            {empty}
          </p>
        ) : (
          <div className="space-y-2">
            {buckets.map((bucket, index) => (
              <details
                key={bucket.category}
                className="group rounded-xl border border-surface-border bg-white open:bg-surface-muted/50"
                open={index === 0}
              >
                <summary className="cursor-pointer list-none px-4 py-3.5">
                  <div className="flex items-center gap-3">
                    <span
                      className={`h-2.5 w-2.5 shrink-0 rounded-full ${dot}`}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-surface-foreground">
                        {bucket.label}
                      </p>
                      <p className="mt-0.5 text-xs text-surface-subtle">
                        {bucket.claims.length} observations from{' '}
                        {bucket.sourceCount} scored answers
                      </p>
                    </div>
                    <span className="rounded-full bg-surface-muted px-2 py-1 text-xs tabular-nums text-surface-subtle group-open:bg-white">
                      {bucket.claims.length}
                    </span>
                    <span className="text-sm text-surface-subtle transition-transform group-open:rotate-180">
                      ⌄
                    </span>
                  </div>
                </summary>
                <ul className="space-y-2 border-t border-surface-border px-4 py-3">
                  {bucket.claims.map((claim) => (
                    <li
                      key={claim}
                      className="flex gap-2.5 text-sm leading-6 text-surface-subtle"
                    >
                      <span
                        className={`mt-2.5 h-1.5 w-1.5 shrink-0 rounded-full ${dot}`}
                      />
                      <span>{claim}</span>
                    </li>
                  ))}
                </ul>
              </details>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}
