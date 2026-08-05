'use client'

import { useEffect, useMemo, useState } from 'react'
import EmptyPanel from '@/components/site-audit/shared/EmptyPanel'
import {
  getPageHealthStatus,
  getPageIssueCounts,
  getPageStatusLabel,
} from '@/components/site-audit/siteAuditUtils'
import type { PageHealthStatus } from '@/components/site-audit/siteAuditUtils'
import type { SiteAuditPage } from '@/lib/contracts'

type PageFilter = 'all' | 'with_issues' | PageHealthStatus
const PAGE_SIZE = 25

const STATUS_TONE: Record<PageHealthStatus, string> = {
  healthy: 'bg-success-soft text-success-strong',
  broken: 'bg-danger-soft text-danger-strong',
  has_issues: 'bg-warning-soft text-warning-strong',
  redirect: 'bg-primary-soft text-primary-strong',
  blocked: 'bg-surface-muted text-surface-subtle',
}

export default function SiteAuditCrawledPagesPanel({
  pages,
}: {
  pages: SiteAuditPage[]
}) {
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<PageFilter>('all')
  const [currentPage, setCurrentPage] = useState(1)

  useEffect(() => setCurrentPage(1), [filter, query])

  const filteredPages = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    return pages.filter((page) => {
      const status = getPageHealthStatus(page)
      const matchesQuery =
        !normalizedQuery ||
        page.final_url.toLowerCase().includes(normalizedQuery) ||
        page.title.toLowerCase().includes(normalizedQuery)
      if (!matchesQuery) return false
      if (filter === 'all') return true
      if (filter === 'with_issues') return page.issues.length > 0
      return status === filter
    })
  }, [filter, pages, query])

  const totalPages = Math.max(1, Math.ceil(filteredPages.length / PAGE_SIZE))
  const safePage = Math.min(currentPage, totalPages)
  const visiblePages = filteredPages.slice(
    (safePage - 1) * PAGE_SIZE,
    safePage * PAGE_SIZE,
  )

  return (
    <div className="space-y-4">
      <div className="grid gap-3 rounded-xl border border-surface-border bg-surface p-4 shadow-sm sm:grid-cols-[1fr_220px]">
        <label>
          <span className="sr-only">Search crawled pages</span>
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search URL or title"
            className="h-11 w-full rounded-lg border border-surface-subtle bg-white px-4 text-sm text-surface-foreground placeholder:text-surface-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          />
        </label>
        <label>
          <span className="sr-only">Filter crawled pages</span>
          <select
            value={filter}
            onChange={(event) => setFilter(event.target.value as PageFilter)}
            className="h-11 w-full rounded-lg border border-surface-subtle bg-white px-3 text-sm text-surface-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            <option value="all">All pages</option>
            <option value="with_issues">With issues</option>
            <option value="healthy">Healthy</option>
            <option value="has_issues">Have issues</option>
            <option value="broken">Crawl failed</option>
            <option value="redirect">Redirected</option>
            <option value="blocked">Blocked by robots</option>
          </select>
        </label>
      </div>

      <section className="overflow-hidden rounded-xl border border-surface-border bg-surface shadow-sm">
        <div className="flex flex-wrap items-end justify-between gap-3 border-b border-surface-border px-5 py-4 sm:px-6">
          <div>
            <h2 className="text-xl font-semibold text-surface-foreground">
              Crawled pages
            </h2>
            <p className="mt-1 text-sm text-surface-subtle">
              {filteredPages.length} of {pages.length} unique page results
            </p>
          </div>
        </div>

        {!pages.length ? (
          <EmptyPanel
            title="No crawled pages available"
            message="This audit has not returned any page results yet."
          />
        ) : !filteredPages.length ? (
          <EmptyPanel
            title="No matching pages"
            message="Try changing the search phrase or selected filter."
          />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="min-w-[900px] w-full border-collapse text-left text-sm">
                <caption className="sr-only">
                  Pages crawled in this audit with HTTP, health, and issue totals
                </caption>
                <thead className="bg-surface-zebra text-xs font-medium uppercase tracking-wide text-surface-subtle">
                  <tr>
                    <th scope="col" className="px-5 py-3 sm:px-6">Page</th>
                    <th scope="col" className="px-4 py-3">HTTP</th>
                    <th scope="col" className="px-4 py-3">Page health</th>
                    <th scope="col" className="px-4 py-3">Title</th>
                    <th scope="col" className="px-5 py-3 sm:px-6">Findings</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-border">
                  {visiblePages.map((page) => (
                    <PageRow key={page.id} page={page} />
                  ))}
                </tbody>
              </table>
            </div>
            {totalPages > 1 ? (
              <div className="flex items-center justify-between gap-4 border-t border-surface-border px-5 py-4 text-sm sm:px-6">
                <span className="text-surface-subtle">
                  Page {safePage} of {totalPages}
                </span>
                <div className="flex gap-2">
                  <button
                    type="button"
                    disabled={safePage === 1}
                    onClick={() => setCurrentPage(safePage - 1)}
                    className="min-h-[40px] rounded-md border border-surface-border px-3 font-medium text-surface-foreground hover:bg-surface-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-50"
                  >
                    Previous
                  </button>
                  <button
                    type="button"
                    disabled={safePage === totalPages}
                    onClick={() => setCurrentPage(safePage + 1)}
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

function PageRow({ page }: { page: SiteAuditPage }) {
  const status = getPageHealthStatus(page)
  const counts = getPageIssueCounts(page)
  const httpLabel = page.status_code > 0 ? String(page.status_code) : '—'

  return (
    <tr className="align-top">
      <th scope="row" className="max-w-sm px-5 py-4 font-normal sm:px-6">
        <a
          href={page.final_url}
          target="_blank"
          rel="noreferrer"
          title={page.final_url}
          className="block truncate font-medium text-primary hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          {page.final_url}
        </a>
      </th>
      <td className="px-4 py-4 text-surface-foreground">{httpLabel}</td>
      <td className="px-4 py-4">
        <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${STATUS_TONE[status]}`}>
          {getPageStatusLabel(status)}
        </span>
      </td>
      <td className="max-w-xs px-4 py-4 text-surface-subtle">
        <span className="block truncate" title={page.title || 'Untitled page'}>
          {page.title || 'Untitled page'}
        </span>
      </td>
      <td className="whitespace-nowrap px-5 py-4 text-xs text-surface-subtle sm:px-6">
        <span className="text-danger-strong">{counts.error} errors</span>
        {' · '}
        <span className="text-warning-strong">{counts.warning} warnings</span>
        {' · '}
        <span>{counts.notice} notices</span>
      </td>
    </tr>
  )
}
