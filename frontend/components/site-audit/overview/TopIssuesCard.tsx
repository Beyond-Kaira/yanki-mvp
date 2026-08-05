import Button from '@/components/Button'
import SeverityBadge from '@/components/site-audit/shared/SeverityBadge'
import type { GroupedAuditIssue } from '@/components/site-audit/siteAuditUtils'

export default function TopIssuesCard({
  issues,
  onViewAll,
}: {
  issues: GroupedAuditIssue[]
  onViewAll: () => void
}) {
  return (
    <article className="overflow-hidden rounded-xl border border-surface-border bg-surface shadow-sm">
      <div className="border-b border-surface-border px-5 py-4 sm:px-6">
        <h2 className="text-xl font-semibold text-surface-foreground">
          Top issues
        </h2>
        <p className="mt-1 text-xs text-surface-subtle">
          Issue types ordered by severity and affected page count.
        </p>
      </div>

      {issues.length ? (
        <ul className="divide-y divide-surface-border">
          {issues.slice(0, 6).map((issue) => (
            <li
              key={issue.id}
              className="grid gap-3 px-5 py-4 sm:grid-cols-[100px_1fr_auto] sm:items-center sm:px-6"
            >
              <SeverityBadge severity={issue.severity} />
              <div className="min-w-0">
                <p className="font-medium text-surface-foreground">
                  {issue.message}
                </p>
                <p className="mt-1 font-mono text-xs text-surface-subtle">
                  {issue.code}
                </p>
              </div>
              <p className="text-sm font-medium text-primary-strong">
                {issue.count} {issue.count === 1 ? 'page' : 'pages'}
              </p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="p-6 text-sm text-surface-subtle">
          No page issues were recorded for this audit.
        </p>
      )}

      {issues.length ? (
        <div className="flex justify-center border-t border-surface-border bg-surface-zebra p-3">
          <Button variant="ghost" size="sm" onClick={onViewAll}>
            View all issues
          </Button>
        </div>
      ) : null}
    </article>
  )
}
