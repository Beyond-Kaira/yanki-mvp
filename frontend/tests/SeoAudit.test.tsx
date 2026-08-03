import { describe, it, expect } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import SeoAudit from '@/components/SeoAudit'
import type { SeoAudit as SeoAuditData, SeoCheck } from '@/lib/contracts'

// A single check, defaulting to a passing HTTPS check. Each fixture overrides
// `id` so the keyed list stays unique.
function check(overrides: Partial<SeoCheck> = {}): SeoCheck {
  return {
    id: 'c1',
    check_id: 'https',
    title: 'Served over HTTPS',
    severity: 'critical',
    status: 'pass',
    detail: 'The site is served over HTTPS.',
    evidence: null,
    ...overrides,
  }
}

function seo(overrides: Partial<SeoAuditData> = {}): SeoAuditData {
  return {
    status: 'ok',
    score: 100,
    grade: 'A',
    checks: [],
    ...overrides,
  }
}

// The flagship failure: robots.txt blocks a retrieval crawler. Copied from the
// backend's `_check_ai_crawlers` so the test asserts against the real evidence.
const aiCrawlerFail = check({
  id: 'ai',
  check_id: 'ai_crawler_access',
  title: 'AI crawlers can read the site',
  severity: 'critical',
  status: 'fail',
  detail:
    'robots.txt blocks crawlers that answer engines use to retrieve and cite ' +
    'pages. While that stands, this site cannot appear in their answers — no ' +
    'amount of content or ranking changes that.',
  evidence: 'Blocked: OAI-SearchBot (ChatGPT Search)',
})

describe('SeoAudit', () => {
  it('shows the grade as the headline for a healthy, all-passing audit', async () => {
    const user = userEvent.setup()
    render(
      <SeoAudit
        seo={seo({
          score: 100,
          grade: 'A',
          checks: [
            check({ id: 'crawl', check_id: 'ai_crawler_access', title: 'AI crawlers can read the site' }),
            check({ id: 'srv', check_id: 'server_rendered_content', title: 'Content is in the HTML, not just JavaScript' }),
            check({ id: 'title', check_id: 'title_present', title: 'Homepage has a title', severity: 'important' }),
          ],
        })}
      />,
    )

    expect(
      screen.getByRole('heading', { name: 'AI readiness audit' }),
    ).toBeInTheDocument()
    // The grade — not the number — is the headline.
    expect(screen.getByText('A')).toBeInTheDocument()
    expect(
      screen.getByText(/Weighted score 100 \/ 100 across 3 scored checks\./),
    ).toBeInTheDocument()

    // A healthy audit has nothing failing and nothing capping the grade.
    expect(screen.queryByText(/Failing checks/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Capped at/)).not.toBeInTheDocument()

    // Passing checks are tucked into a collapsed disclosure, revealed on demand.
    expect(screen.queryByText('Served over HTTPS')).not.toBeInTheDocument()
    const toggle = screen.getByRole('button', { name: /show passing checks \(3\)/i })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await user.click(toggle)
    expect(screen.getByText('Homepage has a title')).toBeInTheDocument()
  })

  it('caps the grade on a single critical failure and shows the failing check with its evidence', () => {
    render(
      <SeoAudit
        seo={seo({
          // A weighted score that would band as B on its own...
          score: 82,
          // ...but the published grade is capped to C by the one critical fail.
          grade: 'C',
          checks: [
            aiCrawlerFail,
            check({ id: 'srv', check_id: 'server_rendered_content', title: 'Content is in the HTML, not just JavaScript' }),
            check({ id: 'title', check_id: 'title_present', title: 'Homepage has a title', severity: 'important' }),
          ],
        })}
      />,
    )

    // The capped grade is the headline, and the cap is explained, not hidden.
    expect(screen.getByText('C')).toBeInTheDocument()
    expect(
      screen.getByText(/Capped at C: one critical check is failing/),
    ).toBeInTheDocument()

    // The failing check, its rationale and its evidence are all visible.
    expect(screen.getByText('Failing checks (1)')).toBeInTheDocument()
    expect(screen.getByText('AI crawlers can read the site')).toBeInTheDocument()
    expect(
      screen.getByText(/this site cannot appear in their answers/),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Blocked: OAI-SearchBot (ChatGPT Search)'),
    ).toBeInTheDocument()
  })

  it('caps the grade at F once two critical checks fail', () => {
    render(
      <SeoAudit
        seo={seo({
          score: 45,
          grade: 'F',
          checks: [
            aiCrawlerFail,
            check({
              id: 'idx',
              check_id: 'indexable',
              title: 'Page is not marked noindex',
              severity: 'critical',
              status: 'fail',
              detail: 'The homepage tells search engines not to index it.',
              evidence: 'meta robots: noindex | X-Robots-Tag: -',
            }),
            check({ id: 'title', check_id: 'title_present', title: 'Homepage has a title', severity: 'important' }),
          ],
        })}
      />,
    )

    expect(screen.getByText('F')).toBeInTheDocument()
    expect(
      screen.getByText(/Capped at F: 2 critical checks are failing/),
    ).toBeInTheDocument()
    expect(screen.getByText('Failing checks (2)')).toBeInTheDocument()
    expect(screen.getByText('AI crawlers can read the site')).toBeInTheDocument()
    expect(screen.getByText('Page is not marked noindex')).toBeInTheDocument()
  })

  it('presents the ai_crawler_access failure as a critical, failed check with its block list', () => {
    render(
      <SeoAudit
        seo={seo({
          score: 80,
          grade: 'C',
          checks: [
            aiCrawlerFail,
            check({ id: 'title', check_id: 'title_present', title: 'Homepage has a title', severity: 'important' }),
          ],
        })}
      />,
    )

    const row = screen
      .getByText('AI crawlers can read the site')
      .closest('li')
    expect(row).not.toBeNull()
    const inRow = within(row as HTMLElement)
    // Severity, status and evidence all sit on the flagship's own row.
    expect(inRow.getByText('Critical')).toBeInTheDocument()
    expect(inRow.getByText('Failed')).toBeInTheDocument()
    expect(
      inRow.getByText('Blocked: OAI-SearchBot (ChatGPT Search)'),
    ).toBeInTheDocument()
  })

  it('renders not_measured and not_applicable distinctly, and never as a failure', async () => {
    const user = userEvent.setup()
    render(
      <SeoAudit
        seo={seo({
          score: 100,
          grade: 'A',
          checks: [
            check({ id: 'title', check_id: 'title_present', title: 'Homepage has a title', severity: 'important' }),
            check({
              id: 'crawl',
              check_id: 'ai_crawler_access',
              title: 'AI crawlers can read the site',
              severity: 'critical',
              status: 'not_measured',
              detail: 'We could not read robots.txt, so we cannot say what it permits.',
              evidence: null,
            }),
            check({
              id: 'alt',
              check_id: 'image_alt',
              title: 'Images have alt text',
              severity: 'minor',
              status: 'not_applicable',
              detail: 'The crawled pages have no images.',
              evidence: null,
            }),
          ],
        })}
      />,
    )

    // Nothing failed, so "Failed" appears nowhere — the excluded checks are not
    // dressed up as failures.
    expect(screen.queryByText(/Failing checks/)).not.toBeInTheDocument()
    expect(screen.queryByText('Failed')).not.toBeInTheDocument()

    // The two excluded checks live behind one disclosure, counted together.
    const toggle = screen.getByRole('button', { name: /show not scored \(2\)/i })
    await user.click(toggle)

    // Distinct badges: "we could not read the input" vs "does not apply here".
    expect(screen.getByText('Not measured')).toBeInTheDocument()
    expect(screen.getByText('Not applicable')).toBeInTheDocument()
    expect(
      screen.getByText('Left out of the score — we could not read the input.'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Left out of the score — this check does not apply here.'),
    ).toBeInTheDocument()
    // Still no failure anywhere after the excluded checks are on screen.
    expect(screen.queryByText('Failed')).not.toBeInTheDocument()
  })

  it('says there is no grade when nothing could be scored, without drawing a zero', () => {
    render(
      <SeoAudit
        seo={seo({
          status: 'ok',
          score: null,
          grade: null,
          checks: [
            check({
              id: 'crawl',
              check_id: 'ai_crawler_access',
              title: 'AI crawlers can read the site',
              severity: 'critical',
              status: 'not_measured',
              detail: 'We could not read robots.txt, so we cannot say what it permits.',
              evidence: null,
            }),
            check({
              id: 'alt',
              check_id: 'image_alt',
              title: 'Images have alt text',
              severity: 'minor',
              status: 'not_applicable',
              detail: 'The crawled pages have no images.',
              evidence: null,
            }),
          ],
        })}
      />,
    )

    expect(
      screen.getByText(/checks could be scored, so there is no/),
    ).toBeInTheDocument()
    // No grade tile and no invented score.
    expect(screen.queryByText('AI readiness grade')).not.toBeInTheDocument()
    expect(screen.queryByText(/Weighted score/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /show not scored \(2\)/i })).toBeInTheDocument()
  })

  it('explains a run that produced no audit at all', () => {
    render(<SeoAudit seo={seo({ status: 'no_crawl', score: null, grade: null, checks: [] })} />)

    expect(
      screen.getByText(/There was no crawl to audit for this run/),
    ).toBeInTheDocument()
    // With no checks there is neither a grade tile nor any disclosure.
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.queryByText(/Weighted score/)).not.toBeInTheDocument()
  })
})
