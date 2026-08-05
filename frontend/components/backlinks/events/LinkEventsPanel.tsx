'use client'

import { useEffect, useState } from 'react'
import {
  EVENT_TONE,
  formatCount,
  formatDate,
  formatMetric,
} from '@/components/backlinks/backlinkUtils'
import EmptyPanel from '@/components/site-audit/shared/EmptyPanel'
import { listLinkEvents } from '@/lib/api'
import type { LinkEvent } from '@/lib/contracts'

const PAGE_SIZE = 25

export default function LinkEventsPanel({ projectId }: { projectId: string }) {
  const [rows, setRows] = useState<LinkEvent[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [kind, setKind] = useState('')
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [message, setMessage] = useState('')

  useEffect(() => setOffset(0), [kind])

  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false
    setStatus('loading')

    listLinkEvents(
      projectId,
      { kind: kind || undefined, limit: PAGE_SIZE, offset },
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
            : 'Link changes could not be loaded.',
        )
        setStatus('error')
      })

    return () => {
      cancelled = true
      controller.abort()
    }
  }, [kind, offset, projectId])

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-surface-border bg-surface p-4 shadow-sm sm:max-w-xs">
        <label>
          <span className="sr-only">Filter link changes</span>
          <select
            value={kind}
            onChange={(event) => setKind(event.target.value)}
            className="h-11 w-full rounded-lg border border-surface-subtle bg-white px-3 text-sm text-surface-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            <option value="">All changes</option>
            <option value="new">New links</option>
            <option value="lost">Lost links</option>
            <option value="regained">Regained links</option>
            <option value="changed">Changed links</option>
          </select>
        </label>
      </div>

      <section className="overflow-hidden rounded-xl border border-surface-border bg-surface shadow-sm">
        <div className="border-b border-surface-border px-5 py-4 sm:px-6">
          <h2 className="text-xl font-semibold text-surface-foreground">
            New &amp; lost links
          </h2>
          <p className="mt-1 text-sm text-surface-subtle">
            {status === 'ready'
              ? `${formatCount(total)} recorded change${total === 1 ? '' : 's'}`
              : 'Loading…'}
          </p>
        </div>

        {status === 'error' ? (
          <EmptyPanel title="Link changes could not be loaded" message={message} />
        ) : status === 'loading' ? (
          <p role="status" className="p-6 text-sm text-surface-subtle sm:p-8">
            Loading link changes…
          </p>
        ) : !rows.length ? (
          <EmptyPanel
            title="No link changes recorded"
            message="Changes accrue from the second refresh onward — the first one has nothing to compare against."
          />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="min-w-[820px] w-full border-collapse text-left text-sm">
                <caption className="sr-only">
                  Backlinks gained, lost, regained or changed, most recent first
                </caption>
                <thead className="bg-surface-zebra text-xs font-medium uppercase tracking-wide text-surface-subtle">
                  <tr>
                    <th scope="col" className="px-5 py-3 sm:px-6">Change</th>
                    <th scope="col" className="px-4 py-3">Source page</th>
                    <th scope="col" className="px-4 py-3">Authority</th>
                    <th scope="col" className="px-4 py-3">Reason</th>
                    <th scope="col" className="px-5 py-3 sm:px-6">When</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-border">
                  {rows.map((row) => (
                    <tr key={row.id} className="align-top">
                      <td className="whitespace-nowrap px-5 py-4 sm:px-6">
                        <span
                          className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium capitalize ${
                            EVENT_TONE[row.kind] ?? 'bg-surface-muted text-surface-subtle'
                          }`}
                        >
                          {row.kind}
                        </span>
                      </td>
                      <th scope="row" className="max-w-sm px-4 py-4 font-normal">
                        <a
                          href={row.source_url}
                          target="_blank"
                          rel="noreferrer nofollow"
                          title={row.source_url}
                          className="block truncate font-medium text-primary hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                        >
                          {row.source_domain}
                        </a>
                      </th>
                      <td className="px-4 py-4 text-surface-foreground">
                        {formatMetric(
                          row.authority_at_event === null ||
                            row.authority_at_event === undefined
                            ? null
                            : Math.round(row.authority_at_event),
                        )}
                      </td>
                      <td className="px-4 py-4 text-xs text-surface-subtle">
                        {row.reason ? row.reason.replace(/_/g, ' ') : '—'}
                        {/* 'lost' without verification is stated as such: the
                            backend refuses to call an unverified absence a
                            confirmed loss, and the UI must not upgrade it. */}
                        {row.kind === 'lost' && !row.verified ? (
                          <span className="mt-0.5 block text-surface-subtle">
                            not re-verified
                          </span>
                        ) : null}
                      </td>
                      <td className="whitespace-nowrap px-5 py-4 text-surface-subtle sm:px-6">
                        {formatDate(row.occurred_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
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
