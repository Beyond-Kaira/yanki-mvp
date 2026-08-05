'use client'

import { useEffect, useState } from 'react'
import {
  TOXICITY_TONE,
  bandOf,
  formatCount,
  formatDate,
  formatMetric,
  readReasons,
} from '@/components/backlinks/backlinkUtils'
import ExportButton from '@/components/backlinks/shared/ExportButton'
import EmptyPanel from '@/components/site-audit/shared/EmptyPanel'
import { downloadDisavowFile, listReferringDomains } from '@/lib/api'
import type { ReferringDomain } from '@/lib/contracts'

const PAGE_SIZE = 25

export default function ReferringDomainsPanel({
  projectId,
}: {
  projectId: string
}) {
  const [rows, setRows] = useState<ReferringDomain[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [band, setBand] = useState('')
  const [sort, setSort] = useState('authority')
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [message, setMessage] = useState('')

  useEffect(() => setOffset(0), [band, sort])

  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false
    setStatus('loading')

    listReferringDomains(
      projectId,
      { band: band || undefined, sort, limit: PAGE_SIZE, offset },
      controller.signal,
    )
      .then((page) => {
        if (cancelled) return
        setRows(page.items)
        setTotal(page.total)
        setStatus('ready')
      })
      .catch((error: unknown) => {
        if (cancelled || (error instanceof Error && error.name === 'AbortError')) {
          return
        }
        setMessage(
          error instanceof Error
            ? error.message
            : 'Referring domains could not be loaded.',
        )
        setStatus('error')
      })

    return () => {
      cancelled = true
      controller.abort()
    }
  }, [band, offset, projectId, sort])

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1

  return (
    <div className="space-y-4">
      <div className="grid gap-3 rounded-xl border border-surface-border bg-surface p-4 shadow-sm sm:grid-cols-[1fr_1fr_auto]">
        <label>
          <span className="sr-only">Filter by toxicity band</span>
          <select
            value={band}
            onChange={(event) => setBand(event.target.value)}
            className="h-11 w-full rounded-lg border border-surface-subtle bg-white px-3 text-sm text-surface-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            <option value="">All toxicity bands</option>
            <option value="high">High risk only</option>
            <option value="medium">Medium risk only</option>
            <option value="low">Low risk only</option>
          </select>
        </label>
        <label>
          <span className="sr-only">Sort referring domains</span>
          <select
            value={sort}
            onChange={(event) => setSort(event.target.value)}
            className="h-11 w-full rounded-lg border border-surface-subtle bg-white px-3 text-sm text-surface-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            <option value="authority">Highest authority</option>
            <option value="links">Most links</option>
            <option value="toxicity">Most toxic</option>
            <option value="domain">Domain A–Z</option>
          </select>
        </label>
        <ExportButton
          label="Export disavow file"
          download={() => downloadDisavowFile(projectId)}
        />
      </div>

      <section className="overflow-hidden rounded-xl border border-surface-border bg-surface shadow-sm">
        <div className="border-b border-surface-border px-5 py-4 sm:px-6">
          <h2 className="text-xl font-semibold text-surface-foreground">
            Referring domains
          </h2>
          <p className="mt-1 text-sm text-surface-subtle">
            {status === 'ready'
              ? `${formatCount(total)} matching domain${total === 1 ? '' : 's'}`
              : 'Loading…'}
          </p>
        </div>

        {status === 'error' ? (
          <EmptyPanel
            title="Referring domains could not be loaded"
            message={message}
          />
        ) : status === 'loading' ? (
          <p role="status" className="p-6 text-sm text-surface-subtle sm:p-8">
            Loading referring domains…
          </p>
        ) : !rows.length ? (
          <EmptyPanel
            title="No matching referring domains"
            message="Try a different filter, or run a refresh to pull the latest profile."
          />
        ) : (
          <>
            <ul className="divide-y divide-surface-border">
              {rows.map((row) => (
                <DomainRow key={row.id} row={row} />
              ))}
            </ul>
            {totalPages > 1 ? (
              <div className="flex items-center justify-between gap-4 border-t border-surface-border px-5 py-4 text-sm sm:px-6">
                <span className="text-surface-subtle">
                  Page {currentPage} of {totalPages}
                </span>
                <div className="flex gap-2">
                  <button
                    type="button"
                    disabled={offset === 0}
                    onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                    className="min-h-[40px] rounded-md border border-surface-border px-3 font-medium text-surface-foreground hover:bg-surface-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-50"
                  >
                    Previous
                  </button>
                  <button
                    type="button"
                    disabled={currentPage >= totalPages}
                    onClick={() => setOffset(offset + PAGE_SIZE)}
                    className="min-h-[40px] rounded-md border border-surface-border px-3 font-medium text-surface-foreground hover:bg-surface-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-50"
                  >
                    Next
                  </button>
                </div>
              </div>
            ) : null}
          </>
        )}
      </section>
    </div>
  )
}

function DomainRow({ row }: { row: ReferringDomain }) {
  const band = row.toxicity_band ? bandOf(row.toxicity_band) : null
  const reasons = readReasons(row.toxicity_reasons)

  return (
    <li className="px-5 py-4 sm:px-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-medium text-surface-foreground">
            {row.referring_domain}
          </p>
          <p className="mt-1 text-xs text-surface-subtle">
            {formatCount(row.links_count)} link
            {row.links_count === 1 ? '' : 's'} ·{' '}
            {formatCount(row.follow_links)} follow · authority{' '}
            {formatMetric(
              row.domain_authority === null || row.domain_authority === undefined
                ? null
                : Math.round(row.domain_authority),
            )}{' '}
            · first linked {formatDate(row.first_linked_at)}
          </p>
        </div>
        {band ? (
          <span
            className={`inline-flex shrink-0 rounded-full px-2.5 py-1 text-xs font-medium capitalize ${TOXICITY_TONE[band]}`}
          >
            {band} risk {formatMetric(row.toxicity_score)}
          </span>
        ) : (
          <span className="shrink-0 text-xs text-surface-subtle">not assessed</span>
        )}
      </div>

      {/* The reasons are always shown alongside the band, never behind a click.
          An unexplained "toxic" label is the category's known credibility trap,
          and a flag people act on without reading is worse than no flag. */}
      {reasons.length ? (
        <ul className="mt-3 space-y-1 border-l-2 border-surface-border pl-3">
          {reasons.map((reason) => (
            <li key={reason.code || reason.label} className="text-xs">
              <span className="font-medium text-surface-foreground">
                {reason.label}
              </span>
              {reason.evidence ? (
                <span className="text-surface-subtle"> — {reason.evidence}</span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </li>
  )
}
