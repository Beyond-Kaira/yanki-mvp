import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { BacklinkSummary, SeoProjectDetail } from '@/lib/contracts'

/**
 * The backlink profile screen.
 *
 * What this file is really guarding is the module's central honesty problem,
 * moved up into the UI. The backend is careful never to state a number it did
 * not measure — nullable scores, an explicit `measurable` flag, toxicity bands
 * that always carry their reasons — and every one of those guarantees can be
 * thrown away by a renderer that prints `0` for `null` or hides a caveat.
 *
 * The other thing it guards is the OFF state. `BACKLINKS_ENABLED` is off in
 * production, so "no index connected" is the state most customers will actually
 * see, and it must read as a configuration fact rather than as a broken page.
 */

const mockedUseAuth = vi.hoisted(() => vi.fn())
const mockedGetSeoProject = vi.hoisted(() => vi.fn())
const mockedGetBacklinkSummary = vi.hoisted(() => vi.fn())
const mockedRefreshBacklinks = vi.hoisted(() => vi.fn())
const mockedDownloadCsv = vi.hoisted(() => vi.fn())

// Hoisted with the mocks that reference it — `vi.mock` factories are lifted to
// the top of the file, so an ordinary top-level class would not exist yet.
const FakeApiError = vi.hoisted(
  () =>
    class FakeApiError extends Error {
      status: number
      constructor(message: string, status: number) {
        super(message)
        this.name = 'ApiError'
        this.status = status
      }
    },
)

vi.mock('next/navigation', () => ({
  useParams: () => ({ projectId: 'p-1' }),
}))

vi.mock('@/components/AuthProvider', () => ({
  useAuth: mockedUseAuth,
}))

vi.mock('@/lib/api', () => ({
  ApiError: FakeApiError,
  getSeoProject: mockedGetSeoProject,
  getBacklinkSummary: mockedGetBacklinkSummary,
  refreshBacklinks: mockedRefreshBacklinks,
  downloadBacklinkCsv: mockedDownloadCsv,
  downloadDisavowFile: vi.fn(),
  listBacklinks: vi.fn().mockResolvedValue({ total: 0, limit: 25, offset: 0, items: [] }),
  listReferringDomains: vi
    .fn()
    .mockResolvedValue({ total: 0, limit: 25, offset: 0, items: [] }),
  listLinkEvents: vi.fn().mockResolvedValue({ total: 0, limit: 25, offset: 0, items: [] }),
  getBacklinkOpportunities: vi
    .fn()
    .mockResolvedValue({ link_gap: [], unlinked_mentions: [], provenance: {} }),
}))

import BacklinkProfileDetail from '@/components/backlinks/detail/BacklinkProfileDetail'

const PROJECT: SeoProjectDetail = {
  id: 'p-1',
  name: 'Acme',
  domain: 'https://acme.test/',
  created_at: '2026-08-01T09:00:00Z',
  updated_at: '2026-08-01T09:00:00Z',
  latest_audit: null,
  audits: [],
}

const SUMMARY: BacklinkSummary = {
  subject_domain: 'acme.test',
  backlinks: 128,
  follow_links: 96,
  referring_domains: 34,
  lost_links: 5,
  authority: 41,
  authority_version: 'ya-1',
  authority_components: {
    reach: { weight: 45, normalized: 0.5, points: 22.5, explains: '34 referring domain(s)' },
    quality: { weight: 30, normalized: 0.4, points: 12.0, explains: 'authority of referring domains' },
    caveats: ['Not PageRank, not Google’s view, and not a ranking prediction.'],
  },
  last_import: {
    id: 'i-1',
    status: 'done',
    vendor: 'mock',
    trigger: 'manual',
    coverage_status: 'complete',
    measurable: true,
    rows_ingested: 128,
    reported_total_backlinks: 200,
    reported_total_referring_domains: 40,
    new_in_period: 4,
    lost_in_period: 1,
    cost_usd: '0',
    snapshot_at: '2026-08-05T09:00:00Z',
    completed_at: '2026-08-05T09:00:00Z',
    error: null,
    provenance: { vendor: 'mock' },
  },
  velocity: [
    { at: '2026-08-05T09:00:00Z', new: 4, lost: 1, reported_total: 200, measurable: true, authority: 41 },
  ],
  anchors: {
    total: 128,
    counts: { brand: 80, exact: 40, generic: 8 },
    shares: { brand: 0.625, exact: 0.3125, generic: 0.0625 },
    money_anchor_share: 0.3125,
  },
  toxicity: { low: 30, medium: 3, high: 1 },
}

describe('BacklinkProfileDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedUseAuth.mockReturnValue({ status: 'authenticated', user: null })
    mockedGetSeoProject.mockResolvedValue(PROJECT)
  })

  it('reads a 404 on a project that DOES load as "not switched on", not an error', async () => {
    // The kill switch and an unknown project both answer 404 on purpose, so the
    // only way to tell them apart is that the project itself loaded fine.
    mockedGetBacklinkSummary.mockRejectedValue(new FakeApiError('Not Found', 404))
    render(<BacklinkProfileDetail />)

    expect(
      await screen.findByRole('heading', { name: /backlinks are not switched on yet/i }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('treats a missing project as a genuine error', async () => {
    mockedGetSeoProject.mockRejectedValue(
      new FakeApiError("We couldn't find that SEO project.", 404),
    )
    render(<BacklinkProfileDetail />)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /couldn't find that SEO project/i,
    )
    expect(
      screen.queryByRole('heading', { name: /not switched on yet/i }),
    ).not.toBeInTheDocument()
  })

  it('does not treat a 500 as "switched off"', async () => {
    mockedGetBacklinkSummary.mockRejectedValue(new FakeApiError('Server error', 500))
    render(<BacklinkProfileDetail />)

    expect(await screen.findByRole('alert')).toHaveTextContent(/server error/i)
  })

  it('shows the headline profile numbers with their provenance', async () => {
    mockedGetBacklinkSummary.mockResolvedValue(SUMMARY)
    render(<BacklinkProfileDetail />)

    expect(await screen.findByRole('heading', { name: 'Acme' })).toBeInTheDocument()
    expect(screen.getByText('128')).toBeInTheDocument()
    expect(screen.getByText('34')).toBeInTheDocument()
    // Which index, when, and whether the pull was complete — the three things
    // that decide what a number is worth.
    expect(screen.getByText(/source:/i)).toHaveTextContent(/mock/)
    expect(screen.getByText(/source:/i)).toHaveTextContent(/complete pull/i)
  })

  it('publishes the authority decomposition and its caveats, not just the score', async () => {
    mockedGetBacklinkSummary.mockResolvedValue(SUMMARY)
    render(<BacklinkProfileDetail />)

    await screen.findByRole('heading', { name: /yanki authority/i })
    expect(screen.getByText('Reach')).toBeInTheDocument()
    expect(screen.getByText(/34 referring domain/i)).toBeInTheDocument()
    // The caveat is the part a score like this is usually missing.
    expect(screen.getByText(/not pagerank/i)).toBeInTheDocument()
  })

  it('renders a missing authority as an em dash rather than a confident zero', async () => {
    mockedGetBacklinkSummary.mockResolvedValue({
      ...SUMMARY,
      authority: null,
      authority_version: null,
      authority_components: null,
    })
    render(<BacklinkProfileDetail />)

    await screen.findByRole('heading', { name: 'Acme' })
    // The label appears twice — the header stat and the overview card — so scope
    // to the header's definition list rather than matching on text alone.
    const term = screen
      .getAllByText('Yanki Authority')
      .find((element) => element.tagName === 'DT')
    expect(term?.parentElement).toHaveTextContent('—')
    expect(term?.parentElement).not.toHaveTextContent('0')
  })

  it('warns when a pull was incomplete instead of implying nothing changed', async () => {
    mockedGetBacklinkSummary.mockResolvedValue({
      ...SUMMARY,
      last_import: {
        ...SUMMARY.last_import!,
        measurable: false,
        coverage_status: 'partial',
      },
    })
    render(<BacklinkProfileDetail />)

    await screen.findByRole('heading', { name: 'Acme' })
    expect(screen.getByText(/incomplete pull/i)).toHaveTextContent(
      /no losses claimed/i,
    )
  })

  it('flags an over-concentrated money-anchor profile', async () => {
    mockedGetBacklinkSummary.mockResolvedValue(SUMMARY)
    render(<BacklinkProfileDetail />)

    await screen.findByRole('heading', { name: /anchor text/i })
    expect(screen.getByText(/over-optimization pattern/i)).toBeInTheDocument()
  })

  it('says toxicity is advisory and never auto-disavowed', async () => {
    mockedGetBacklinkSummary.mockResolvedValue(SUMMARY)
    render(<BacklinkProfileDetail />)

    await screen.findByRole('heading', { name: /^toxicity$/i })
    expect(screen.getByText(/advisory only/i)).toHaveTextContent(
      /nothing is disavowed automatically/i,
    )
  })

  it('moves between tabs', async () => {
    const user = userEvent.setup()
    mockedGetBacklinkSummary.mockResolvedValue(SUMMARY)
    render(<BacklinkProfileDetail />)

    await screen.findByRole('heading', { name: 'Acme' })
    await user.click(screen.getByRole('tab', { name: /referring domains/i }))

    await waitFor(() => {
      // Anchored: the empty state's "No matching referring domains" is also a
      // heading, and an unanchored match finds both.
      expect(
        screen.getByRole('heading', { name: /^referring domains$/i }),
      ).toBeInTheDocument()
    })
  })

  it('reports an unmeasurable refresh honestly rather than as a success', async () => {
    const user = userEvent.setup()
    mockedGetBacklinkSummary.mockResolvedValue(SUMMARY)
    mockedRefreshBacklinks.mockResolvedValue({
      import_id: 'i-2',
      measurable: false,
      coverage_status: 'partial',
      rows_ingested: 10,
      new_links: 0,
      lost_links: 0,
      regained_links: 0,
      changed_links: 0,
      cost_usd: '0',
    })
    render(<BacklinkProfileDetail />)

    await screen.findByRole('heading', { name: 'Acme' })
    await user.click(screen.getByRole('button', { name: /^refresh$/i }))

    expect(await screen.findByRole('status')).toHaveTextContent(
      /incomplete profile/i,
    )
  })

  it('explains an export refused for lack of permission, in the app', async () => {
    // The export is a FETCH, not a link, precisely so this failure lands here.
    // A plain <a href> would carry no bearer token, 401 as a page navigation,
    // and show the customer a raw error body instead of this sentence.
    const user = userEvent.setup()
    mockedGetBacklinkSummary.mockResolvedValue(SUMMARY)
    mockedDownloadCsv.mockRejectedValue(
      new FakeApiError(
        'Your role cannot export backlinks. Exporting is a separate permission from viewing.',
        403,
      ),
    )
    render(<BacklinkProfileDetail />)

    await screen.findByRole('heading', { name: 'Acme' })
    await user.click(screen.getByRole('button', { name: /export csv/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /separate permission from viewing/i,
    )
  })

  it('explains a quota refusal in the customer’s terms', async () => {
    const user = userEvent.setup()
    mockedGetBacklinkSummary.mockResolvedValue(SUMMARY)
    mockedRefreshBacklinks.mockRejectedValue(
      new FakeApiError(
        'This organization has used its backlink refreshes for the month.',
        429,
      ),
    )
    render(<BacklinkProfileDetail />)

    await screen.findByRole('heading', { name: 'Acme' })
    await user.click(screen.getByRole('button', { name: /^refresh$/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /used its backlink refreshes/i,
    )
  })
})
