import type { SiteAuditIssue } from '@/lib/contracts'

const TONE: Record<SiteAuditIssue['severity'], string> = {
  error: 'bg-danger-soft text-danger-strong',
  warning: 'bg-warning-soft text-warning-strong',
  notice: 'bg-surface-muted text-surface-subtle',
}

export default function SeverityBadge({
  severity,
}: {
  severity: SiteAuditIssue['severity']
}) {
  return (
    <span
      className={`inline-flex w-fit rounded-full px-2.5 py-1 text-xs font-medium capitalize ${TONE[severity]}`}
    >
      {severity}
    </span>
  )
}
