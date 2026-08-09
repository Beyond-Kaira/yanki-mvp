'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { ApiError, listAnalyses } from '@/lib/api'
import type { AnalysisList, AnalysisSummary } from '@/lib/contracts'

const PAGE_SIZE = 20

const STATUS_FILTERS: { id: string; label: string }[] = [
  { id: '', label: 'All' },
  { id: 'done', label: 'Finished' },
  { id: 'running', label: 'Running' },
  { id: 'queued', label: 'Queued' },
  { id: 'failed', label: 'Failed' },
]

const STATUS_TONE: Record<string, string> = {
  done: 'bg-success-soft text-success-strong',
  running: 'bg-primary-soft text-primary-strong',
  queued: 'bg-surface-muted text-surface-subtle',
  failed: 'bg-danger-soft text-danger-strong',
}

function formatMoment(value: string): string {
  return new Date(value).toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** The submitted URL without its scheme — the part a reader scans for. */
function readableTarget(url: string): string {
  return url.replace(/^https?:\/\//, '').replace(/\/$/, '')
}

/**
 * The organization's analysis history.
 *
 * **The screen exists because the data started belonging to someone.** Runs have
 * carried an `org_id` since P7.6, and until now the only way back to a result
 * was the URL you happened to be redirected to — so closing the tab lost it
 * (tech-debt #77). Everything here follows from that: it is a way back, not a
 * dashboard.
 *
 * **A missing score renders as an em dash, never a zero.** A queued run has not
 * been measured; a run that scored zero is a much worse and entirely different
 * fact. Rendering `null` as `0` would tell a customer their brand is invisible
 * when the truth is that we have not looked yet. Same rule the Backlinks screens
 * follow, and it is the one thing in this file worth never relaxing.
 *
 * **Paging is server-side and the total is the server's.** "1–20 of 47" counts
 * what the filter matched, not what this page happens to hold.
 */
export default function AnalysisHistoryClient() {
  const [page, setPage] = useState<AnalysisList | null>(null)
  const [status, setStatus] = useState('')
  const [offset, setOffset] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(
    (signal?: AbortSignal) => {
      setLoading(true)
      setError(null)
      listAnalyses({ status: status || undefined, limit: PAGE_SIZE, offset }, signal)
        .then((result) => {
          setPage(result)
          setLoading(false)
        })
        .catch((cause: unknown) => {
          if (cause instanceof Error && cause.name === 'AbortError') return
          setError(
            cause instanceof ApiError
              ? cause.message
              : "We couldn't load your analyses.",
          )
          setLoading(false)
        })
    },
    [status, offset],
  )

  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal)
    return () => controller.abort()
  }, [load])

  const rows: AnalysisSummary[] = page?.analyses ?? []
  const total = page?.total ?? 0
  const showingFrom = total === 0 ? 0 : offset + 1
  const showingTo = Math.min(offset + PAGE_SIZE, total)

  return (
    <section aria-labelledby="history-heading" className="mx-auto max-w-5xl px-6 py-10 sm:px-8">
      <header className="mb-6">
        <h1 id="history-heading" className="text-2xl font-semibold tracking-tight">
          Your analyses
        </h1>
        <p className="mt-1 text-sm text-surface-subtle">
          Every GEO analysis your organization has run. Open one to see the prompts,
          the raw engine answers and the score behind it.
        </p>
      </header>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">Status</span>
        {STATUS_FILTERS.map((filter) => (
          <button
            key={filter.id || 'all'}
            type="button"
            aria-pressed={status === filter.id}
            onClick={() => {
              setStatus(filter.id)
              setOffset(0)
            }}
            className={`h-9 rounded-md border px-3 text-sm ${
              status === filter.id
                ? 'border-primary bg-primary-soft text-primary-strong'
                : 'border-surface-border bg-surface text-surface-foreground'
            }`}
          >
            {filter.label}
          </button>
        ))}
      </div>

      {error ? (
        <p
          role="alert"
          className="rounded-md border border-danger-border bg-danger-soft px-3 py-2 text-sm text-danger-strong"
        >
          {error}
        </p>
      ) : null}

      {loading && page === null ? (
        <p className="text-sm text-surface-subtle">Loading your analyses…</p>
      ) : null}

      {!loading && !error && rows.length === 0 ? (
        <div className="rounded-2xl border border-surface-border bg-surface p-8 text-center">
          <p className="text-base font-medium">
            {status ? 'No analyses with that status yet.' : 'No analyses yet.'}
          </p>
          <p className="mt-1 text-sm text-surface-subtle">
            {status
              ? 'Try a different status filter.'
              : 'Run your first one from the dashboard and it will appear here.'}
          </p>
          {status ? null : (
            <Link
              href="/dashboard"
              className="mt-4 inline-block font-medium text-primary-strong underline underline-offset-2"
            >
              Start an analysis
            </Link>
          )}
        </div>
      ) : null}

      {rows.length > 0 ? (
        <div className="overflow-x-auto rounded-2xl border border-surface-border bg-surface">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">
              Your organization&rsquo;s analyses, newest first
            </caption>
            <thead className="border-b border-surface-border text-surface-subtle">
              <tr>
                <th scope="col" className="px-4 py-3 font-medium">
                  Target
                </th>
                <th scope="col" className="px-4 py-3 font-medium">
                  Status
                </th>
                <th scope="col" className="px-4 py-3 font-medium">
                  GEO score
                </th>
                <th scope="col" className="px-4 py-3 font-medium">
                  Started
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-b border-surface-border last:border-0">
                  <td className="px-4 py-3">
                    <Link
                      href={`/analyses/${row.id}`}
                      className="font-medium text-primary-strong underline underline-offset-2"
                    >
                      {readableTarget(row.url)}
                    </Link>
                    {row.status === 'failed' && row.error ? (
                      <span className="mt-1 block text-xs text-surface-subtle">
                        {row.error}
                      </span>
                    ) : null}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                        STATUS_TONE[row.status] ?? 'bg-surface-muted text-surface-subtle'
                      }`}
                    >
                      {row.status}
                    </span>
                    {row.status === 'running' ? (
                      <span className="ml-2 text-xs text-surface-subtle">
                        {row.progress}%
                      </span>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 tabular-nums">
                    {/* Never `row.geo_score ?? 0` — see the component docstring. */}
                    {row.geo_score === null || row.geo_score === undefined
                      ? '—'
                      : row.geo_score.toFixed(1)}
                  </td>
                  <td className="px-4 py-3 text-surface-subtle">
                    {formatMoment(row.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {total > 0 ? (
        <nav aria-label="Pagination" className="mt-4 flex items-center justify-between">
          <p className="text-sm text-surface-subtle">
            Showing {showingFrom}–{showingTo} of {total}
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              className="h-9 rounded-md border border-surface-border bg-surface px-3 text-sm disabled:opacity-50"
            >
              Previous
            </button>
            <button
              type="button"
              disabled={offset + PAGE_SIZE >= total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
              className="h-9 rounded-md border border-surface-border bg-surface px-3 text-sm disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </nav>
      ) : null}
    </section>
  )
}
