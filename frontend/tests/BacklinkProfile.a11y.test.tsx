import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { BacklinkSummary, SeoProjectDetail } from '@/lib/contracts'
import { axeCheck } from './a11y'

const mockedUseAuth = vi.hoisted(() => vi.fn())
const mockedGetSeoProject = vi.hoisted(() => vi.fn())
const mockedGetBacklinkSummary = vi.hoisted(() => vi.fn())

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
  refreshBacklinks: vi.fn(),
  downloadBacklinkCsv: vi.fn(),
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
    caveats: ['Not PageRank.'],
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
    {
      at: '2026-08-05T09:00:00Z',
      new: 4,
      lost: 1,
      reported_total: 200,
      measurable: true,
      authority: 41,
    },
  ],
  anchors: {
    total: 128,
    counts: { brand: 80, exact: 40 },
    shares: { brand: 0.625, exact: 0.375 },
    money_anchor_share: 0.375,
  },
  toxicity: { low: 30, medium: 3, high: 1 },
}

describe('Backlink profile accessibility', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedUseAuth.mockReturnValue({ status: 'authenticated', user: null })
    mockedGetSeoProject.mockResolvedValue(PROJECT)
  })

  it('has no axe violations on a loaded profile', async () => {
    mockedGetBacklinkSummary.mockResolvedValue(SUMMARY)
    const { container } = render(<BacklinkProfileDetail />)

    await screen.findByRole('heading', { name: 'Acme' })
    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('has no axe violations in the switched-off state', async () => {
    // The state most customers see today, so it gets the same scrutiny as the
    // populated one rather than being treated as an error path.
    mockedGetBacklinkSummary.mockRejectedValue(new FakeApiError('Not Found', 404))
    const { container } = render(<BacklinkProfileDetail />)

    await screen.findByRole('heading', { name: /not switched on yet/i })
    expect(await axeCheck(container)).toHaveNoViolations()
  })
})
