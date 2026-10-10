import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import IndustryCitationsSetup from '@/app/ai-visibility/industry-citations/IndustryCitationsSetup'
import {
  fetchIndustryRanking,
  fetchIndustrySectors,
  type IndustryRanking,
} from '@/lib/industry-citations'

vi.mock('@/lib/industry-citations', () => ({
  fetchIndustryRanking: vi.fn(),
  fetchIndustrySectors: vi.fn(),
}))
const report: IndustryRanking = {
  sector: 'e-commerce',
  scope: 'Across organizations',
  methodology: 'Verified stored citations.',
  candidate_responses: 4,
  eligible_responses: 3,
  distinct_questions: 2,
  excluded_responses: { unknown_provenance: 1 },
  rejected_citations: {},
  site_count: 1,
  page_count: 1,
  offset: 0,
  limit: 25,
  page_limit_per_site: 50,
  sites: [
    {
      domain: 'source.test',
      page_count: 1,
      response_count: 2,
      question_count: 1,
      response_coverage: 66.67,
      model_counts: { 'model-a': 2 },
      pages: [
        {
          url: 'https://source.test/guide',
          response_count: 2,
          question_count: 1,
          response_coverage: 66.67,
          model_counts: { 'model-a': 2 },
        },
      ],
    },
  ],
}

async function selectIndustry(value = 'e-commerce') {
  await screen.findByRole('option', { name: /e-commerce/ })
  fireEvent.change(screen.getByLabelText('Industry'), { target: { value } })
}

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(fetchIndustrySectors).mockResolvedValue([
    { sector: 'e-commerce', record_count: 4 },
    { sector: 'artificial intelligence', record_count: 5 },
  ])
  vi.mocked(fetchIndustryRanking).mockResolvedValue(report)
})

describe('industry ranking screen', () => {
  it('loads available sectors and renders sources with expandable pages', async () => {
    render(<IndustryCitationsSetup />)
    await selectIndustry()
    expect(await screen.findByText('1. source.test')).toBeInTheDocument()
    expect(fetchIndustryRanking).toHaveBeenCalledWith(
      'e-commerce',
      0,
      expect.any(AbortSignal),
    )
    const summary = screen.getByText('1. source.test').closest('summary')!
    fireEvent.click(summary)
    expect(summary.parentElement).toHaveAttribute('open')
    expect(
      screen.getByRole('link', { name: 'https://source.test/guide' }),
    ).toHaveAttribute('href', 'https://source.test/guide')
    expect(screen.getByText(/Live origin not verified/)).toHaveTextContent('1')
    expect(
      screen.queryByRole('button', { name: 'Generate questions' }),
    ).not.toBeInTheDocument()
  })

  it('explains unverified records instead of inventing a ranking', async () => {
    vi.mocked(fetchIndustryRanking).mockResolvedValue({
      ...report,
      eligible_responses: 0,
      sites: [],
      site_count: 0,
      page_count: 0,
    })
    render(<IndustryCitationsSetup />)
    await selectIndustry()
    expect(await screen.findByText(/none currently meet/)).toBeInTheDocument()
    expect(screen.queryByText('Most cited websites')).not.toBeInTheDocument()
  })

  it('discards a late response for a previous sector', async () => {
    let resolve!: (value: IndustryRanking) => void
    vi.mocked(fetchIndustryRanking)
      .mockReturnValueOnce(
        new Promise((done) => {
          resolve = done
        }),
      )
      .mockResolvedValueOnce({
        ...report,
        sector: 'artificial intelligence',
        sites: [],
        site_count: 0,
      })
    render(<IndustryCitationsSetup />)
    await selectIndustry()
    await selectIndustry('artificial intelligence')
    await screen.findByText(/no citations passed verification/)
    resolve(report)
    await waitFor(() =>
      expect(screen.queryByText('1. source.test')).not.toBeInTheDocument(),
    )
  })

  it('retries errors and supports pagination', async () => {
    vi.mocked(fetchIndustryRanking)
      .mockRejectedValueOnce(new Error('Temporarily unavailable'))
      .mockResolvedValue({ ...report, site_count: 30 })
    render(<IndustryCitationsSetup />)
    await selectIndustry()
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Temporarily unavailable',
    )
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    await screen.findByText('1. source.test')
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() =>
      expect(fetchIndustryRanking).toHaveBeenLastCalledWith(
        'e-commerce',
        25,
        expect.any(AbortSignal),
      ),
    )
  })

  it('shows an empty sector catalog', async () => {
    vi.mocked(fetchIndustrySectors).mockResolvedValue([])
    render(<IndustryCitationsSetup />)
    expect(
      await screen.findByText('No industry data is available yet.'),
    ).toBeInTheDocument()
    expect(fetchIndustryRanking).not.toHaveBeenCalled()
  })
})
