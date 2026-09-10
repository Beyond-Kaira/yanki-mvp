import Link from 'next/link'
import type { SeoProjectDetail, SiteAuditDetail } from '@/lib/contracts'

const UPDATED_FORMATTER = new Intl.DateTimeFormat('en', {
  weekday: 'short',
  month: 'short',
  day: 'numeric',
  year: 'numeric',
})

function formatUpdatedAt(value: string): string | null {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : UPDATED_FORMATTER.format(date)
}

export default function SiteAuditProjectHeader({
  project,
  audit,
  action,
}: {
  project: SeoProjectDetail
  audit: SiteAuditDetail | null
  action?: React.ReactNode
}) {
  return (
    <header className="space-y-1">
      <Link
        href="/site-audit"
        className="inline-flex min-h-[36px] items-center text-xs font-medium text-primary-strong transition-colors hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        ← All SEO projects
      </Link>
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
        <h1 className="min-w-0 flex-1 break-words text-3xl font-semibold tracking-tight text-surface-foreground">
          <span className="font-medium text-surface-subtle">Site Audit: </span>
          {project.name}
        </h1>
        {action ? <div className="shrink-0">{action}</div> : null}
      </div>
      {audit ? (
        <AuditRunMeta project={project} audit={audit} />
      ) : (
        <p className="break-all text-sm text-surface-subtle">{project.domain}</p>
      )}
    </header>
  )
}

function MobileIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      className="h-3.5 w-3.5 flex-none"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="7" y="2" width="10" height="20" rx="2" />
      <line x1="11" y1="18" x2="13" y2="18" />
    </svg>
  )
}

function AuditRunMeta({
  project,
  audit,
}: {
  project: SeoProjectDetail
  audit: SiteAuditDetail
}) {
  const isMobile = audit.profile_id === 'site_audit_mobile'
  const updatedAt = formatUpdatedAt(audit.updated_at)

  const items: { key: string; icon?: React.ReactNode; label: string }[] = [
    { key: 'domain', label: project.domain },
  ]
  if (updatedAt) items.push({ key: 'updated', label: `Updated: ${updatedAt}` })
  items.push({
    key: 'profile',
    icon: isMobile ? <MobileIcon /> : undefined,
    label: isMobile ? 'Mobile' : 'Desktop',
  })
  items.push({
    key: 'js-rendering',
    label: `JS rendering: ${audit.js_rendering ? 'Enabled' : 'Disabled'}`,
  })
  items.push({
    key: 'pages-crawled',
    label: `Pages crawled: ${audit.pages_crawled}/${audit.page_limit}`,
  })

  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-surface-subtle">
      {items.map((item, index) => (
        <span
          key={item.key}
          className={`flex items-center gap-1.5 ${item.key === 'domain' ? 'break-all' : ''}`}
        >
          {index > 0 ? (
            <span aria-hidden="true" className="text-surface-border">
              ·
            </span>
          ) : null}
          {item.icon}
          {item.label}
        </span>
      ))}
    </div>
  )
}
