'use client'

import type { PerformanceState } from '@/components/site-audit/hooks/useSearchConsoleConnection'

/**
 * Four numbers and the window they cover.
 *
 * The rule this component exists to hold: **a null is not a zero.** The backend
 * returns `ctr` and `position` as null when there were no impressions, because
 * an average over nothing is not zero and a position of 0 renders as "ranked
 * above the first result". Both are drawn as an em dash, and the `no_data` state
 * says so in words rather than showing four confident zeros.
 *
 * No chart, no query table, no page table. `top_queries` and `top_pages` are in
 * the contract and typed, and deliberately not rendered here — that is the next
 * slice, and half a table is worse than none.
 */
export default function SearchConsolePerformanceSummary({
  state,
}: {
  state: PerformanceState
}) {
  if (state.kind === 'idle') return null

  if (state.kind === 'loading') {
    return (
      <p role="status" className="mt-4 text-sm text-surface-subtle">
        Loading Search Console performance…
      </p>
    )
  }

  if (state.kind === 'error') {
    return (
      <p
        role="alert"
        className="mt-4 rounded-lg bg-danger-soft p-3 text-sm text-danger-strong"
      >
        {state.message}
      </p>
    )
  }

  const { performance } = state

  if (performance.data_state === 'no_data') {
    return (
      <div className="mt-4 rounded-lg border border-surface-border bg-surface-muted p-4">
        <p className="text-sm text-surface-foreground">
          No Search Console data for this period.
        </p>
        <p className="mt-1 text-xs text-surface-subtle">
          {formatRange(performance.start_date, performance.end_date)}
        </p>
      </div>
    )
  }

  return (
    <div className="mt-4">
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Metric label="Clicks" value={formatCount(performance.summary.clicks)} />
        <Metric label="Impressions" value={formatCount(performance.summary.impressions)} />
        <Metric label="CTR" value={formatCtr(performance.summary.ctr)} />
        <Metric label="Average position" value={formatPosition(performance.summary.position)} />
      </dl>
      <p className="mt-3 text-xs text-surface-subtle">
        {formatRange(performance.start_date, performance.end_date)}
      </p>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-surface-border bg-white p-3">
      <dt className="text-xs font-medium text-surface-subtle">{label}</dt>
      <dd className="mt-1 text-xl font-semibold tabular-nums text-surface-foreground">
        {value}
      </dd>
    </div>
  )
}

function formatCount(value: number): string {
  return Math.round(value).toLocaleString('en-US')
}

/** An em dash, never "0%" — see the module docstring. */
function formatCtr(value: number | null): string {
  if (value === null) return '—'
  return `${(value * 100).toFixed(1)}%`
}

function formatPosition(value: number | null): string {
  if (value === null) return '—'
  return value.toFixed(1)
}

function formatRange(startDate: string, endDate: string): string {
  return `${startDate} to ${endDate}`
}
