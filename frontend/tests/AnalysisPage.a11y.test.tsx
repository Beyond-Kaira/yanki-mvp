import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { Analysis } from '@/lib/contracts'
import { axeCheck } from './a11y'

vi.mock('next/navigation', () => ({
  useParams: () => ({ id: 'test-id' }),
}))

vi.mock('@/lib/api', () => ({
  getAnalysis: vi.fn(),
  joinWaitlist: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number
    constructor(message: string, status: number) {
      super(message)
      this.name = 'ApiError'
      this.status = status
    }
  },
}))

import AnalysisPage from '@/app/analyses/[id]/page'
import { getAnalysis } from '@/lib/api'

const mockedGet = vi.mocked(getAnalysis)

function makeAnalysis(overrides: Partial<Analysis>): Analysis {
  return {
    id: 'test-id',
    url: 'https://example.com',
    status: 'running',
    current_step: 'prompts',
    progress: 30,
    error: null,
    created_at: '2026-07-09T00:00:00Z',
    updated_at: '2026-07-09T00:00:00Z',
    result: {
      footprint_count: null,
      geo_score: null,
      kyc: null,
      prompts: [],
      responses: [],
      total_responses: null,
      engine_presence: null,
      competitors_appeared: null,
          serp: null,
    },
    ...overrides,
  } as Analysis
}

describe('AnalysisPage accessibility', () => {
  beforeEach(() => {
    mockedGet.mockReset()
  })

  it('has no axe violations while running', async () => {
    mockedGet.mockResolvedValue(
      makeAnalysis({ status: 'running', progress: 30, current_step: 'prompts' }),
    )
    const { container } = render(<AnalysisPage />)
    await screen.findByRole('progressbar')
    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('announces the failure card as an alert with no axe violations', async () => {
    mockedGet.mockResolvedValue(
      makeAnalysis({
        status: 'failed',
        progress: 0,
        current_step: null,
        error: 'The pipeline hit an unrecoverable error.',
      }),
    )
    const { container } = render(<AnalysisPage />)

    // A3: the failure card is announced on every entry path via role="alert".
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/couldn't finish this analysis/i)
    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('has no axe violations on the results screen', async () => {
    mockedGet.mockResolvedValue(
      makeAnalysis({
        status: 'done',
        progress: 100,
        current_step: null,
        result: {
          footprint_count: 1,
          geo_score: 0.5,
          kyc: null,
          prompts: [{ id: 'p1', category: 'comparison', text: 'Best CRM?' }],
          responses: [
            {
              id: 'r1',
              engine: 'openai',
              model: 'gpt-4o-mini',
              footprint: true,
              matched_snippet: 'Acme is a strong option.',
              prompt_id: 'p1',
              raw_text: 'Acme is a strong option and…',
              cost_usd: 0.0021,
            },
          ],
          total_responses: 2,
          engine_presence: null,
          competitors_appeared: null,
          serp: null,
        },
      }),
    )
    const { container } = render(<AnalysisPage />)
    await screen.findByRole('img') // the ScoreGauge
    // The growth-loop waitlist section renders below the results on done.
    expect(
      screen.getByRole('heading', { name: /track this score over time/i }),
    ).toBeInTheDocument()
    expect(await axeCheck(container)).toHaveNoViolations()
  })
})
