'use client'

import { useState } from 'react'
import Button from '@/components/Button'
import { formatCount, formatDate, formatMetric } from '@/components/backlinks/backlinkUtils'
import ExportButton from '@/components/backlinks/shared/ExportButton'
import { ApiError, downloadBacklinkCsv, refreshBacklinks } from '@/lib/api'
import type { BacklinkSummary, SeoProjectDetail } from '@/lib/contracts'

export default function BacklinkProfileHeader({
  project,
  summary,
  onRefreshed,
}: {
  project: SeoProjectDetail
  summary: BacklinkSummary
  onRefreshed: () => void
}) {
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const lastImport = summary.last_import

  async function refresh() {
    setRefreshing(true)
    setError(null)
    setNotice(null)
    try {
      const result = await refreshBacklinks(project.id)
      // An unmeasurable pull is reported, not hidden. It is exactly the case
      // where the numbers did NOT move, and a customer who is not told why will
      // read a flat chart as a broken product.
      setNotice(
        result.measurable
          ? `Refreshed — ${formatCount(result.rows_ingested)} links read, ${formatCount(result.new_links)} new, ${formatCount(result.lost_links)} lost.`
          : `Refreshed, but the index returned an incomplete profile (${result.coverage_status}). Nothing was recorded as lost.`,
      )
      onRefreshed()
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : 'The refresh could not be started.',
      )
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <header>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-surface-subtle">Backlinks</p>
          <h1 className="mt-1 text-3xl font-semibold text-surface-foreground">
            {project.name}
          </h1>
          <p className="mt-1 text-sm text-surface-subtle">
            {summary.subject_domain}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <ExportButton
            label="Export CSV"
            download={() => downloadBacklinkCsv(project.id)}
          />
          <Button onClick={refresh} loading={refreshing}>
            {refreshing ? 'Refreshing…' : 'Refresh'}
          </Button>
        </div>
      </div>

      {error ? (
        <p
          role="alert"
          className="mt-4 rounded-lg border border-danger bg-danger-soft px-4 py-3 text-sm text-danger-strong"
        >
          {error}
        </p>
      ) : null}
      {notice ? (
        <p
          role="status"
          className="mt-4 rounded-lg border border-surface-border bg-surface-muted px-4 py-3 text-sm text-surface-foreground"
        >
          {notice}
        </p>
      ) : null}

      <dl className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Backlinks" value={formatCount(summary.backlinks)} />
        <Stat
          label="Referring domains"
          value={formatCount(summary.referring_domains)}
        />
        <Stat
          label="Yanki Authority"
          value={formatMetric(summary.authority)}
          hint={summary.authority_version ?? undefined}
        />
        <Stat label="Lost links" value={formatCount(summary.lost_links)} />
      </dl>

      {/* Provenance is not a footnote. Which index said this, when, and whether
          that pull was complete are the three things that decide how much a
          number is worth — and the difference between us and a tool that says
          "our index of 40 trillion links". */}
      <p className="mt-4 text-xs text-surface-subtle">
        {lastImport ? (
          <>
            Source: <span className="font-medium">{lastImport.vendor}</span> ·
            fetched {formatDate(lastImport.snapshot_at)} ·{' '}
            {lastImport.measurable ? (
              <>complete pull</>
            ) : (
              <span className="text-warning-strong">
                incomplete pull ({lastImport.coverage_status}) — no losses claimed
                from it
              </span>
            )}
          </>
        ) : (
          <>No import has run for this project yet.</>
        )}
      </p>
    </header>
  )
}

function Stat({
  label,
  value,
  hint,
}: {
  label: string
  value: string
  hint?: string
}) {
  return (
    // A `div` grouping inside a `dl` may contain ONLY dt/dd — a stray <p> here
    // is a real markup error, and axe fails the whole page for it. The hint
    // therefore lives inside the dd rather than beside it.
    <div className="rounded-xl border border-surface-border bg-surface p-4 shadow-sm">
      <dt className="text-sm text-surface-subtle">{label}</dt>
      <dd className="mt-1 text-2xl font-semibold text-surface-foreground">
        {value}
        {hint ? (
          <span className="mt-1 block text-xs font-normal text-surface-subtle">
            {hint}
          </span>
        ) : null}
      </dd>
    </div>
  )
}
