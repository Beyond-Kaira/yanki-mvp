import Link from 'next/link'
import type { SeoProjectDetail, SiteAuditDetail } from '@/lib/contracts'

const STATUS_LABEL: Record<SiteAuditDetail['status'], string> = {
  queued: 'Queued',
  running: 'Running',
  done: 'Complete',
  failed: 'Failed',
}

const STATUS_TONE: Record<SiteAuditDetail['status'], string> = {
  queued: 'bg-surface-muted text-surface-subtle',
  running: 'bg-primary-soft text-primary-strong',
  done: 'bg-success-soft text-success-strong',
  failed: 'bg-danger-soft text-danger-strong',
}

export default function SiteAuditProjectHeader({
  project,
  audit,
}: {
  project: SeoProjectDetail
  audit: SiteAuditDetail | null
}) {
  return (
    <div>
      <Link
        href="/site-audit"
        className="inline-flex min-h-[36px] items-center rounded-full bg-primary-soft px-3 text-xs font-medium text-primary-strong transition-colors hover:bg-surface-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        ← All SEO projects
      </Link>
      <header className="mt-3 rounded-xl border border-surface-border bg-surface p-5 shadow-sm sm:p-6">
        <p className="font-mono text-xs font-medium uppercase tracking-[0.18em] text-primary-strong">
          Site Audit project
        </p>
        <h1 className="mt-1.5 break-words text-3xl font-semibold tracking-tight text-surface-foreground">
          {project.name}
        </h1>
        <p className="mt-1.5 break-all text-sm text-surface-subtle">
          {project.domain}
        </p>
        {audit ? <AuditRunMeta audit={audit} /> : null}
      </header>
    </div>
  )
}

function AuditRunMeta({ audit }: { audit: SiteAuditDetail }) {
  const profile = audit.profile_id === 'site_audit_mobile' ? 'Mobile' : 'Desktop'
  return (
    <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-surface-subtle">
      <span className="rounded-full border border-surface-border bg-surface-muted px-3 py-1.5">
        {profile} crawler
      </span>
      <span className="rounded-full border border-surface-border bg-surface-muted px-3 py-1.5">
        JavaScript {audit.js_rendering ? 'enabled' : 'disabled'}
      </span>
      <span className="rounded-full border border-surface-border bg-surface-muted px-3 py-1.5">
        {audit.pages_crawled} unique page {audit.pages_crawled === 1 ? 'result' : 'results'} · limit{' '}
        {audit.page_limit}
      </span>
      <span className={`rounded-full px-3 py-1.5 font-medium ${STATUS_TONE[audit.status]}`}>
        {audit.status === 'running'
          ? `${audit.progress}% complete`
          : STATUS_LABEL[audit.status]}
      </span>
    </div>
  )
}
