import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import SeoAudit from '@/components/SeoAudit'
import type { SeoAudit as SeoAuditData, SeoCheck } from '@/lib/contracts'
import { axeCheck } from './a11y'

// A capped audit that exercises every branch at once: a critical failure, a
// warning, several passes, and both excluded statuses (not measured / not
// applicable). The disclosures start collapsed, matching the default render.
const checks: SeoCheck[] = [
  {
    id: 'ai',
    check_id: 'ai_crawler_access',
    title: 'AI crawlers can read the site',
    severity: 'critical',
    status: 'fail',
    detail:
      'robots.txt blocks crawlers that answer engines use to retrieve and cite pages.',
    evidence: 'Blocked: PerplexityBot (Perplexity)',
  },
  {
    id: 'h1',
    check_id: 'h1_present',
    title: 'Homepage has exactly one H1',
    severity: 'important',
    status: 'warn',
    detail: "There are several H1s, so the page's main subject is ambiguous.",
    evidence: '3 H1 elements',
  },
  {
    id: 'srv',
    check_id: 'server_rendered_content',
    title: 'Content is in the HTML, not just JavaScript',
    severity: 'critical',
    status: 'pass',
    detail: 'The server sends the content.',
    evidence: '4200 characters of server-rendered text',
  },
  {
    id: 'title',
    check_id: 'title_present',
    title: 'Homepage has a title',
    severity: 'important',
    status: 'pass',
    detail: null,
    evidence: 'Acme Robotics — warehouse automation',
  },
  {
    id: 'https',
    check_id: 'https',
    title: 'Served over HTTPS',
    severity: 'critical',
    status: 'pass',
    detail: 'The site is served over HTTPS.',
    evidence: null,
  },
  {
    id: 'sitemap',
    check_id: 'sitemap',
    title: 'A sitemap is advertised',
    severity: 'minor',
    status: 'not_measured',
    detail: 'robots.txt was unreadable.',
    evidence: null,
  },
  {
    id: 'alt',
    check_id: 'image_alt',
    title: 'Images have alt text',
    severity: 'minor',
    status: 'not_applicable',
    detail: 'The crawled pages have no images.',
    evidence: null,
  },
]

// Score bands as B; the published grade is capped to C by the critical failure.
const capped: SeoAuditData = {
  status: 'ok',
  score: 80,
  grade: 'C',
  checks,
}

const notAudited: SeoAuditData = {
  status: 'no_crawl',
  score: null,
  grade: null,
  checks: [],
}

describe('SeoAudit accessibility', () => {
  it('has no axe violations across a graded audit with every status', async () => {
    const { container } = render(
      <main>
        <SeoAudit seo={capped} />
      </main>,
    )
    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('has no axe violations once the disclosures are expanded', async () => {
    const user = userEvent.setup()
    const { container } = render(
      <main>
        <SeoAudit seo={capped} />
      </main>,
    )
    await user.click(screen.getByRole('button', { name: /show passing checks/i }))
    await user.click(screen.getByRole('button', { name: /show not scored/i }))
    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('has no axe violations in the not-audited state', async () => {
    const { container } = render(
      <main>
        <SeoAudit seo={notAudited} />
      </main>,
    )
    expect(await axeCheck(container)).toHaveNoViolations()
  })
})
