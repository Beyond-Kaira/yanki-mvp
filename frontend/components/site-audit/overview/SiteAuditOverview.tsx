import type { SeoProjectDetail, SiteAuditDetail } from '@/lib/contracts'
import { formatDelta, groupAuditIssues } from '@/components/site-audit/siteAuditUtils'
import CrawledPagesCard from './CrawledPagesCard'
import IssueTotalsCard from './IssueTotalsCard'
import SiteHealthCard from './SiteHealthCard'
import TopIssuesCard from './TopIssuesCard'

export default function SiteAuditOverview({
  audit,
  project,
  onViewAllIssues,
}: {
  audit: SiteAuditDetail
  project: SeoProjectDetail
  onViewAllIssues: () => void
}) {
  const groupedIssues = groupAuditIssues(audit.pages)
  const currentIndex = project.audits.findIndex((run) => run.id === audit.id)
  const previousAudit =
    currentIndex >= 0
      ? project.audits.slice(currentIndex + 1).find((run) => run.status === 'done')
      : undefined
  const healthDelta = formatDelta(audit.health_score, previousAudit?.health_score)
  const pagesDelta = formatDelta(audit.pages.length, previousAudit?.pages_crawled)

  return (
    <div className="space-y-5">
      {['queued', 'running'].includes(audit.status) ? (
        <section
          role="status"
          aria-live="polite"
          className="rounded-xl border border-primary bg-primary-soft p-5"
        >
          <h2 className="font-semibold text-primary-strong">Audit in progress</h2>
          <p className="mt-1 text-sm text-surface-foreground">
            {audit.current_step ? `Current step: ${audit.current_step}. ` : ''}
            {audit.progress}% complete. This page updates automatically.
          </p>
          <div
            className="mt-3 h-2 overflow-hidden rounded-full bg-surface"
            aria-hidden="true"
          >
            <div
              className="h-full rounded-full bg-primary transition-[width]"
              style={{ width: `${audit.progress}%` }}
            />
          </div>
        </section>
      ) : null}

      {audit.status === 'failed' ? (
        <section
          role="alert"
          className="rounded-xl border border-danger bg-danger-soft p-5"
        >
          <h2 className="font-semibold text-danger-strong">Audit failed</h2>
          <p className="mt-1 text-sm text-surface-foreground">
            {audit.error ?? 'The crawler could not complete this audit.'}
          </p>
        </section>
      ) : null}

      <section
        aria-label="Audit health and crawled pages"
        className="grid gap-5 lg:grid-cols-2"
      >
        <SiteHealthCard score={audit.health_score} delta={healthDelta} />
        <CrawledPagesCard pages={audit.pages} delta={pagesDelta} />
      </section>

      <section
        aria-label="Audit findings"
        className="grid gap-5 lg:grid-cols-[0.7fr_1.3fr]"
      >
        <IssueTotalsCard audit={audit} />
        <TopIssuesCard issues={groupedIssues} onViewAll={onViewAllIssues} />
      </section>
    </div>
  )
}
