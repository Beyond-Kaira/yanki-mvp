import type { SiteAuditPage } from '@/lib/contracts'
import { getAuditPageCounts } from '@/components/site-audit/siteAuditUtils'

const SEGMENTS = [
  { key: 'healthy', label: 'Healthy', color: 'bg-success' },
  { key: 'broken', label: 'Broken', color: 'bg-danger' },
  { key: 'haveIssues', label: 'Have issues', color: 'bg-warning' },
  { key: 'redirects', label: 'Redirected', color: 'bg-primary' },
  { key: 'blocked', label: 'Blocked', color: 'bg-surface-subtle' },
] as const

export default function CrawledPagesCard({
  pages,
  delta,
}: {
  pages: SiteAuditPage[]
  delta?: string | null
}) {
  const counts = getAuditPageCounts(pages)
  const total = pages.length

  return (
    <article className="rounded-xl border border-surface-border bg-surface p-6 shadow-sm">
      <div className="flex items-center gap-1.5">
        <h2 className="text-base font-semibold text-surface-foreground">
          Crawled pages
        </h2>
        <span
          aria-hidden="true"
          title="Unique final URLs stored by the latest audit."
          className="flex h-4 w-4 items-center justify-center rounded-full text-[10px] font-semibold text-surface-subtle ring-1 ring-inset ring-surface-border"
        >
          i
        </span>
      </div>

      <div className="mt-4 flex items-center gap-4">
        <div className="flex items-baseline gap-2 whitespace-nowrap">
          <span className="text-3xl font-semibold tracking-tight text-surface-foreground">
            {total}
          </span>
          <span className="text-xs text-surface-subtle">{delta ?? 'First audit'}</span>
        </div>
        <div
          className="flex h-2.5 flex-1 overflow-hidden rounded-full bg-surface-muted"
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
      </div>

      <ul className="mt-5 space-y-3">
        {SEGMENTS.map((segment) => (
          <li key={segment.key} className="flex items-center gap-2 text-sm">
            <span
              aria-hidden="true"
              className={`h-2.5 w-2.5 rounded-full ${segment.color}`}
            />
            <span className="flex-1 text-surface-subtle">{segment.label}</span>
            <span className="font-semibold text-primary">
              {counts[segment.key]}
            </span>
          </li>
        ))}
      </ul>
    </article>
  )
}
