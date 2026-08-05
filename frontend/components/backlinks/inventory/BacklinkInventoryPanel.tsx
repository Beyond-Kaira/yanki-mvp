'use client'

import { useEffect, useState } from 'react'
import {
  ANCHOR_CLASS_LABELS,
  TOXICITY_TONE,
  bandOf,
  formatCount,
  formatDate,
  formatMetric,
} from '@/components/backlinks/backlinkUtils'
import EmptyPanel from '@/components/site-audit/shared/EmptyPanel'
import { listBacklinks } from '@/lib/api'
import type { Backlink } from '@/lib/contracts'

const PAGE_SIZE = 25

type FollowFilter = 'all' | 'follow' | 'nofollow'

export default function BacklinkInventoryPanel({
  projectId,
}: {
  projectId: string
}) {
  const [rows, setRows] = useState<Backlink[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [anchorClass, setAnchorClass] = useState('')
  const [follow, setFollow] = useState<FollowFilter>('all')
  const [sort, setSort] = useState('authority')
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [message, setMessage] = useState('')

  // Filters reset paging: staying on page 7 of a filter that now matches four
  // rows shows an empty table and reads as "no results" rather than "wrong page".
  useEffect(() => setOffset(0), [anchorClass, follow, sort])

  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false
    setStatus('loading')

    listBacklinks(
      projectId,
      {
        anchor_class: anchorClass || undefined,
        follow: follow === 'all' ? undefined : follow === 'follow',
        sort,
        limit: PAGE_SIZE,
        offset,
      },
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
          error instanceof Error ? error.message : 'Backlinks could not be loaded.',
        )
        setStatus('error')
      })

    return () => {
      cancelled = true
      controller.abort()
    }
  }, [anchorClass, follow, offset, projectId, sort])

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1

  return (
    <div className="space-y-4">
      <div className="grid gap-3 rounded-xl border border-surface-border bg-surface p-4 shadow-sm sm:grid-cols-3">
        <label>
          <span className="sr-only">Filter by anchor class</span>
          <select
            value={anchorClass}
            onChange={(event) => setAnchorClass(event.target.value)}
            className="h-11 w-full rounded-lg border border-surface-subtle bg-white px-3 text-sm text-surface-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            <option value="">All anchor classes</option>
            {Object.entries(ANCHOR_CLASS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="sr-only">Filter by link attribute</span>
          <select
            value={follow}
            onChange={(event) => setFollow(event.target.value as FollowFilter)}
            className="h-11 w-full rounded-lg border border-surface-subtle bg-white px-3 text-sm text-surface-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            <option value="all">Follow and nofollow</option>
            <option value="follow">Follow only</option>
            <option value="nofollow">Nofollow only</option>
          </select>
        </label>
        <label>
          <span className="sr-only">Sort backlinks</span>
          <select
            value={sort}
            onChange={(event) => setSort(event.target.value)}
            className="h-11 w-full rounded-lg border border-surface-subtle bg-white px-3 text-sm text-surface-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            <option value="authority">Highest authority</option>
            <option value="first_seen">Newest first seen</option>
            <option value="last_seen">Most recently seen</option>
            <option value="toxicity">Most toxic</option>
            <option value="domain">Domain A–Z</option>
          </select>
        </label>
      </div>

      <section className="overflow-hidden rounded-xl border border-surface-border bg-surface shadow-sm">
        <div className="border-b border-surface-border px-5 py-4 sm:px-6">
          <h2 className="text-xl font-semibold text-surface-foreground">
            Backlinks
          </h2>
          <p className="mt-1 text-sm text-surface-subtle">
            {/* The total describes the FILTER, not the page — a paged view that
                reports its page size as the total quietly tells a customer they
                have 25 backlinks. */}
            {status === 'ready'
              ? `${formatCount(total)} matching link${total === 1 ? '' : 's'}`
              : 'Loading…'}
          </p>
        </div>

        {status === 'error' ? (
          <EmptyPanel title="Backlinks could not be loaded" message={message} />
        ) : status === 'loading' ? (
          <p role="status" className="p-6 text-sm text-surface-subtle sm:p-8">
            Loading backlinks…
          </p>
        ) : !rows.length ? (
          <EmptyPanel
            title="No matching backlinks"
            message="Try a different filter, or run a refresh to pull the latest profile."
          />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="min-w-[900px] w-full border-collapse text-left text-sm">
                <caption className="sr-only">
                  Backlinks pointing at this project, with anchor, attributes and
                  authority
                </caption>
                <thead className="bg-surface-zebra text-xs font-medium uppercase tracking-wide text-surface-subtle">
                  <tr>
                    <th scope="col" className="px-5 py-3 sm:px-6">Source page</th>
                    <th scope="col" className="px-4 py-3">Anchor</th>
                    <th scope="col" className="px-4 py-3">Type</th>
                    <th scope="col" className="px-4 py-3">Authority</th>
                    <th scope="col" className="px-4 py-3">First seen</th>
                    <th scope="col" className="px-5 py-3 sm:px-6">Toxicity</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-border">
                  {rows.map((row) => (
                    <BacklinkRow key={row.id} row={row} />
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

function BacklinkRow({ row }: { row: Backlink }) {
  const band = row.toxicity_band ? bandOf(row.toxicity_band) : null

  return (
    <tr className="align-top">
      <th scope="row" className="max-w-sm px-5 py-4 font-normal sm:px-6">
        <a
          href={row.source_url}
          target="_blank"
          rel="noreferrer nofollow"
          title={row.source_url}
          className="block truncate font-medium text-primary hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          {row.source_domain}
        </a>
        <span className="block truncate text-xs text-surface-subtle">
          {row.source_url}
        </span>
      </th>
      <td className="max-w-xs px-4 py-4 text-surface-foreground">
        <span className="block truncate" title={row.anchor || 'No anchor text'}>
          {row.anchor || <span className="text-surface-subtle">—</span>}
        </span>
        <span className="text-xs text-surface-subtle">
          {ANCHOR_CLASS_LABELS[row.anchor_class] ?? row.anchor_class}
        </span>
      </td>
      <td className="whitespace-nowrap px-4 py-4">
        <span
          className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${
            row.is_follow
              ? 'bg-success-soft text-success-strong'
              : 'bg-surface-muted text-surface-subtle'
          }`}
        >
          {row.is_follow ? 'follow' : 'nofollow'}
        </span>
      </td>
      <td className="px-4 py-4 text-surface-foreground">
        {formatMetric(
          row.source_domain_authority === null ||
            row.source_domain_authority === undefined
            ? null
            : Math.round(row.source_domain_authority),
        )}
      </td>
      <td className="whitespace-nowrap px-4 py-4 text-surface-subtle">
        {formatDate(row.first_seen_at)}
      </td>
      <td className="whitespace-nowrap px-5 py-4 sm:px-6">
        {band ? (
          <span
            className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium capitalize ${TOXICITY_TONE[band]}`}
          >
            {band} {formatMetric(row.toxicity_score)}
          </span>
        ) : (
          <span className="text-xs text-surface-subtle">not assessed</span>
        )}
      </td>
    </tr>
  )
}
