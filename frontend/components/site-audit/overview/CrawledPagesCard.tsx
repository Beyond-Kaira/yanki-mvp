import type { SiteAuditPage } from '@/lib/contracts'
import { getAuditPageCounts } from '@/components/site-audit/siteAuditUtils'

const SEGMENTS = [
  { key: 'healthy', label: 'Healthy', color: 'bg-success' },
  { key: 'broken', label: 'Broken', color: 'bg-danger' },
  { key: 'haveIssues', label: 'Have issues', color: 'bg-warning' },
  { key: 'redirects', label: 'Redirected', color: 'bg-primary' },
  { key: 'blocked', label: 'Blocked', color: 'bg-surface-subtle' },
] as const

export default function CrawledPagesCard({ pages }: { pages: SiteAuditPage[] }) {
  const counts = getAuditPageCounts(pages)
  const total = pages.length

  return (
    <article className="rounded-xl border border-surface-border bg-surface p-6 shadow-sm">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold text-surface-foreground">
            Crawled page results
          </h2>
          <p className="mt-1 text-xs text-surface-subtle">
            Unique final URLs stored by the latest audit.
          </p>
        </div>
        <p className="text-4xl font-semibold tracking-tight text-surface-foreground">
          {total}
        </p>
      </div>

      <div
        className="mt-7 flex h-3 overflow-hidden rounded-full bg-surface-muted"
        role="img"
        aria-label={SEGMENTS.map(
          (segment) => `${segment.label}: ${counts[segment.key]}`,
        ).join(', ')}
      >
        {SEGMENTS.filter((segment) => counts[segment.key] > 0).map((segment) => (
          <span
            key={segment.key}
            aria-hidden="true"
            className={segment.color}
            style={{ flexGrow: counts[segment.key] }}
          />
        ))}
      </div>

      <ul className="mt-6 grid gap-x-6 gap-y-3 sm:grid-cols-2">
        {SEGMENTS.map((segment) => (
          <li key={segment.key} className="flex items-center gap-2 text-sm">
            <span
              aria-hidden="true"
              className={`h-2.5 w-2.5 rounded-full ${segment.color}`}
            />
            <span className="flex-1 text-surface-subtle">{segment.label}</span>
            <span className="font-semibold text-surface-foreground">
              {counts[segment.key]}
            </span>
          </li>
        ))}
      </ul>
    </article>
  )
}
