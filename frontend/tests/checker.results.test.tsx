import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { Analysis, AnalysisResponse } from '@/lib/contracts'
import { axeCheck } from './a11y'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useParams: () => ({ id: 'check-id' }),
  useSearchParams: () => new URLSearchParams('submission_id=sub-1'),
}))

vi.mock('@/lib/api', () => ({
  createCheckerAnalysis: vi.fn(),
  getAnalysis: vi.fn(),
  submitLead: vi.fn(),
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

import CheckerResultsPage from '@/app/checker/[id]/page'
import { getAnalysis } from '@/lib/api'

const mockedGet = vi.mocked(getAnalysis)

// No casts: the fixture satisfies the generated wire types in full.
function makeAnalysis(overrides: Partial<Analysis>): Analysis {
  return {
    id: 'check-id',
    url: 'checker://notion/note-taking',
    status: 'running',
    current_step: 'prompts',
    progress: 30,
    error: null,
    created_at: '2026-07-10T00:00:00Z',
    updated_at: '2026-07-10T00:00:00Z',
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
      seo: null,
    },
    ...overrides,
  }
}

function response(overrides: Partial<AnalysisResponse>): AnalysisResponse {
  return {
    id: 'r1',
    engine: 'anthropic',
    model: 'mock',
    footprint: true,
    matched_snippet: 'Notion is a strong option.',
    prompt_id: 'p1',
    raw_text: 'Notion is a strong option and…',
    cost_usd: 0,
    ...overrides,
  }
}

describe('Checker results screen', () => {
  beforeEach(() => {
    mockedGet.mockReset()
  })

  it('points at the step a failed check stopped on', async () => {
    mockedGet.mockResolvedValue(
      makeAnalysis({
        status: 'failed',
        current_step: 'execute',
        progress: 45,
        error: 'The engine timed out.',
      }),
    )

    const { container } = render(<CheckerResultsPage />)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/couldn't finish this check/i)
    expect(alert).toHaveTextContent(/stopped while asking the AI engines/i)
    // The trail marks the step that died, and nothing after it.
    expect(screen.getByText('Executing')).toBeInTheDocument()
    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('draws no trail when the check failed before claiming a step', async () => {
    mockedGet.mockResolvedValue(
      makeAnalysis({
        status: 'failed',
        current_step: null,
        progress: 0,
        error: 'The worker died on startup.',
      }),
    )

    render(<CheckerResultsPage />)

    await screen.findByRole('alert')
    // Nothing to point at: the alert carries the outcome alone.
    expect(screen.queryByText('Executing')).not.toBeInTheDocument()
    expect(screen.queryByText(/stopped while/i)).not.toBeInTheDocument()
  })

  it('reports the size of the run above the gated answers', async () => {
    mockedGet.mockResolvedValue(
      makeAnalysis({
        status: 'done',
        current_step: null,
        progress: 100,
        result: {
          footprint_count: 1,
          geo_score: 0.5,
          kyc: null,
          prompts: [{ id: 'p1', category: 'recommendation', text: 'Best?' }],
          responses: [
            response({ id: 'r1', engine: 'anthropic', footprint: true }),
            response({
              id: 'r2',
              engine: 'openai',
              footprint: false,
              matched_snippet: null,
            }),
          ],
          total_responses: 2,
          engine_presence: [
            { engine: 'anthropic', mentioned: 1, total: 1 },
            { engine: 'openai', mentioned: 0, total: 1 },
          ],
          competitors_appeared: [],
          serp: null,
          seo: null,
        },
      }),
    )

    render(<CheckerResultsPage />)

    // The score card the analyses route already had, now shared.
    await screen.findByText('Questions')
    expect(screen.getByText('Answers')).toBeInTheDocument()
    expect(screen.getByText('Mentions')).toBeInTheDocument()
    // The email gate stays the primary conversion and is untouched.
    expect(
      screen.getByRole('heading', { name: /see every answer/i }),
    ).toBeInTheDocument()
  })
})
