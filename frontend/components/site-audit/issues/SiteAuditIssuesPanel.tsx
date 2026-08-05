'use client'

import { useMemo, useState } from 'react'
import SeverityBadge from '@/components/site-audit/shared/SeverityBadge'
import {
  getPageStatusLabel,
  getPageHealthStatus,
  groupAuditIssues,
} from '@/components/site-audit/siteAuditUtils'
import type { GroupedAuditIssue } from '@/components/site-audit/siteAuditUtils'
import type { SiteAuditIssue, SiteAuditPage } from '@/lib/contracts'

type IssueFilter = 'all' | SiteAuditIssue['severity']

const FILTER_LABELS: Record<IssueFilter, string> = {
  all: 'All',
  error: 'Errors',
  warning: 'Warnings',
  notice: 'Notices',
}

export default function SiteAuditIssuesPanel({ pages }: { pages: SiteAuditPage[] }) {
  const groups = useMemo(() => groupAuditIssues(pages), [pages])
  const [filter, setFilter] = useState<IssueFilter>('all')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const selected = groups.find((group) => group.id === selectedId)

  if (selected) {
    return <IssueDetails issue={selected} onBack={() => setSelectedId(null)} />
  }

  const filtered =
    filter === 'all' ? groups : groups.filter((group) => group.severity === filter)
  const findingTotal = filtered.reduce((sum, group) => sum + group.count, 0)
  const filters = (Object.keys(FILTER_LABELS) as IssueFilter[]).map((id) => ({
    id,
    label: FILTER_LABELS[id],
    count: groups
      .filter((group) => id === 'all' || group.severity === id)
      .reduce((sum, group) => sum + group.count, 0),
  }))

  return (
    <div className="space-y-4">
      <fieldset className="flex flex-wrap gap-2">
        <legend className="sr-only">Filter issues</legend>
        {filters.map((item) => (
          <button
            key={item.id}
            type="button"
            aria-pressed={filter === item.id}
            onClick={() => setFilter(item.id)}
            className={`inline-flex min-h-[40px] items-center gap-2 rounded-full border px-4 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
              filter === item.id
                ? 'border-primary bg-primary-soft text-primary-strong'
                : 'border-surface-border bg-surface text-surface-subtle hover:border-surface-subtle hover:text-surface-foreground'
            }`}
          >
            {item.label}
            <span className="rounded-full bg-surface-muted px-2 py-0.5 text-xs text-surface-foreground">
              {item.count}
            </span>
          </button>
        ))}
      </fieldset>

      <section className="overflow-hidden rounded-xl border border-surface-border bg-surface shadow-sm">
        <div className="border-b border-surface-border px-5 py-4 sm:px-6">
          <h2 className="text-xl font-semibold text-surface-foreground">
            {filter === 'all' ? 'All issues' : FILTER_LABELS[filter]}
          </h2>
          <p className="mt-1 text-sm text-surface-subtle">
            {filtered.length} issue {filtered.length === 1 ? 'type' : 'types'} and{' '}
            {findingTotal} findings across {pages.length} crawled pages.
          </p>
        </div>

        {filtered.length ? (
          <ul className="divide-y divide-surface-border">
            {filtered.map((issue) => (
              <li key={issue.id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(issue.id)}
                  className="grid min-h-[72px] w-full gap-3 px-5 py-4 text-left hover:bg-surface-zebra focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary sm:grid-cols-[100px_1fr_auto] sm:items-center sm:px-6"
                >
                  <SeverityBadge severity={issue.severity} />
                  <span className="min-w-0">
                    <span className="block font-medium text-surface-foreground">
                      {issue.message}
                    </span>
                    <span className="mt-1 block font-mono text-xs text-surface-subtle">
                      {issue.code}
                    </span>
                  </span>
                  <span className="text-sm font-medium text-primary-strong">
                    {issue.count} {issue.count === 1 ? 'page' : 'pages'} →
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <div className="p-6 sm:p-8">
            <h3 className="font-semibold text-surface-foreground">
              No matching issues
            </h3>
            <p className="mt-1 text-sm text-surface-subtle">
              This audit has no findings in the selected severity.
            </p>
          </div>
        )}
      </section>
    </div>
  )
}

function IssueDetails({
  issue,
  onBack,
}: {
  issue: GroupedAuditIssue
  onBack: () => void
}) {
  return (
    <div className="space-y-5">
      <button
        type="button"
        onClick={onBack}
        className="inline-flex min-h-[40px] items-center text-sm font-medium text-primary hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        ← Back to all issues
      </button>

      <section className="rounded-xl border border-surface-border bg-surface p-6 shadow-sm sm:p-8">
        <SeverityBadge severity={issue.severity} />
        <h2 className="mt-4 text-2xl font-semibold text-surface-foreground">
          {issue.message}
        </h2>
        <p className="mt-2 font-mono text-xs text-surface-subtle">{issue.code}</p>
        <p className="mt-4 text-sm text-surface-subtle">
          Found on {issue.count} {issue.count === 1 ? 'page' : 'pages'} in the
          latest audit. Rule-specific remediation guidance is not available from
          the backend yet.
        </p>
      </section>

      <section className="overflow-hidden rounded-xl border border-surface-border bg-surface shadow-sm">
        <div className="border-b border-surface-border px-5 py-4 sm:px-6">
          <h3 className="text-lg font-semibold text-surface-foreground">
            Affected pages
          </h3>
        </div>
        <ul className="divide-y divide-surface-border">
          {issue.pages.map((page) => (
            <li
              key={page.id}
              className="grid gap-2 px-5 py-4 sm:grid-cols-[1fr_auto] sm:items-center sm:px-6"
            >
              <div className="min-w-0">
                <a
                  href={page.final_url}
                  target="_blank"
                  rel="noreferrer"
                  className="block truncate font-medium text-primary hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                >
                  {page.final_url}
                </a>
                <p className="mt-1 truncate text-xs text-surface-subtle">
                  {page.title || 'Untitled page'}
                </p>
              </div>
              <span className="text-sm text-surface-subtle">
                {getPageStatusLabel(getPageHealthStatus(page))}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
