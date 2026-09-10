import { describe, expect, it } from 'vitest'
import type { SiteAuditPage } from '@/lib/contracts'
import {
  getAuditPageCounts,
  getPageHealthStatus,
  groupAuditIssues,
} from '@/components/site-audit/siteAuditUtils'

function page(
  id: string,
  statusCode: number,
  issues: SiteAuditPage['issues'] = [],
): SiteAuditPage {
  return {
    id,
    requested_url: `https://example.com/${id}`,
    final_url: `https://example.com/${id}`,
    status_code: statusCode,
    title: id,
    created_at: '2026-08-04T09:00:00Z',
    meta_description: null,
    h1_count: 0,
    html_lang: null,
    issues,
    schemas: [],
  }
}

describe('siteAuditUtils', () => {
  it('classifies a robots-blocked status zero page as blocked, not broken', () => {
    const blocked = page('blocked', 0, [
      {
        code: 'blocked_by_robots',
        severity: 'notice',
        message: 'Blocked by robots.txt.',
        details: {},
      },
    ])

    expect(getPageHealthStatus(blocked)).toBe('blocked')
    expect(getAuditPageCounts([blocked])).toEqual({
      healthy: 0,
      broken: 0,
      haveIssues: 0,
      redirects: 0,
      blocked: 1,
    })
  })

  it('keeps redirects and crawl failures in distinct page health groups', () => {
    expect(
      getPageHealthStatus(
        page('redirect', 200, [
          {
            code: 'url_redirected',
            severity: 'notice',
            message: 'URL redirected.',
            details: {},
          },
        ]),
      ),
    ).toBe('redirect')
    expect(getPageHealthStatus(page('failed', 0))).toBe('broken')
  })

  it('groups repeated rules by severity and code and orders errors first', () => {
    const missingCanonical = {
      code: 'missing_canonical',
      severity: 'error' as const,
      message: 'Canonical link is missing.',
      details: {},
    }
    const groups = groupAuditIssues([
      page('one', 200, [
        {
          code: 'short_title',
          severity: 'warning',
          message: 'Title is too short.',
          details: {},
        },
        missingCanonical,
      ]),
      page('two', 200, [missingCanonical]),
    ])

    expect(groups.map(({ code, count }) => ({ code, count }))).toEqual([
      { code: 'missing_canonical', count: 2 },
      { code: 'short_title', count: 1 },
    ])
  })
})
