import type { SiteAuditIssue, SiteAuditPage } from '@/lib/contracts'

export type PageHealthStatus =
  | 'healthy'
  | 'broken'
  | 'has_issues'
  | 'redirect'
  | 'blocked'

export type IssueCounts = Record<SiteAuditIssue['severity'], number>

export interface AuditPageCounts {
  healthy: number
  broken: number
  haveIssues: number
  redirects: number
  blocked: number
}

export interface GroupedAuditIssue {
  id: string
  code: string
  severity: SiteAuditIssue['severity']
  message: string
  count: number
  pages: SiteAuditPage[]
}

const SEVERITY_RANK: Record<SiteAuditIssue['severity'], number> = {
  error: 0,
  warning: 1,
  notice: 2,
}

export function hasIssueCode(page: SiteAuditPage, code: string): boolean {
  return page.issues.some((issue) => issue.code === code)
}

export function getPageIssueCounts(page: SiteAuditPage): IssueCounts {
  return page.issues.reduce<IssueCounts>(
    (counts, issue) => ({
      ...counts,
      [issue.severity]: counts[issue.severity] + 1,
    }),
    { error: 0, warning: 0, notice: 0 },
  )
}

export function getPageHealthStatus(page: SiteAuditPage): PageHealthStatus {
  if (hasIssueCode(page, 'blocked_by_robots')) return 'blocked'
  if (
    hasIssueCode(page, 'crawl_failed') ||
    page.status_code === 0 ||
    page.status_code >= 400
  ) {
    return 'broken'
  }
  if (
    hasIssueCode(page, 'url_redirected') ||
    (page.status_code >= 300 && page.status_code < 400)
  ) {
    return 'redirect'
  }
  if (page.issues.length > 0) return 'has_issues'
  return 'healthy'
}

export function getAuditPageCounts(pages: SiteAuditPage[]): AuditPageCounts {
  return pages.reduce<AuditPageCounts>(
    (counts, page) => {
      const status = getPageHealthStatus(page)
      if (status === 'healthy') counts.healthy += 1
      if (status === 'broken') counts.broken += 1
      if (status === 'has_issues') counts.haveIssues += 1
      if (status === 'redirect') counts.redirects += 1
      if (status === 'blocked') counts.blocked += 1
      return counts
    },
    { healthy: 0, broken: 0, haveIssues: 0, redirects: 0, blocked: 0 },
  )
}

export function groupAuditIssues(pages: SiteAuditPage[]): GroupedAuditIssue[] {
  const groups = new Map<string, GroupedAuditIssue>()

  for (const page of pages) {
    for (const issue of page.issues) {
      const id = `${issue.severity}:${issue.code}`
      const current = groups.get(id)
      if (current) {
        current.count += 1
        current.pages.push(page)
      } else {
        groups.set(id, {
          id,
          code: issue.code,
          severity: issue.severity,
          message: issue.message,
          count: 1,
          pages: [page],
        })
      }
    }
  }

  return Array.from(groups.values()).sort(
    (left, right) =>
      SEVERITY_RANK[left.severity] - SEVERITY_RANK[right.severity] ||
      right.count - left.count ||
      left.message.localeCompare(right.message),
  )
}

export function formatDelta(
  current: number | null | undefined,
  previous: number | null | undefined,
): string | null {
  if (current == null || previous == null) return null
  const diff = current - previous
  if (diff === 0) return 'no changes'
  return diff > 0 ? `+${diff}` : `${diff}`
}

export function getPageStatusLabel(status: PageHealthStatus): string {
  const labels: Record<PageHealthStatus, string> = {
    healthy: 'Healthy',
    broken: 'Crawl failed',
    has_issues: 'Has issues',
    redirect: 'Redirected',
    blocked: 'Blocked by robots',
  }
  return labels[status]
}
