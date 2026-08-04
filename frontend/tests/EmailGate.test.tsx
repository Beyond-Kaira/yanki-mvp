import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { Analysis } from '@/lib/contracts'

vi.mock('@/lib/api', () => ({
  submitLead: vi.fn(),
  getAnalysis: vi.fn(),
  createCheckerAnalysis: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number
    constructor(message: string, status: number) {
      super(message)
      this.name = 'ApiError'
      this.status = status
    }
  },
}))

vi.mock('next/navigation', () => ({
  useParams: () => ({ id: 'check-id' }),
  useSearchParams: () => new URLSearchParams('submission_id=sub-1'),
  useRouter: () => ({ push: vi.fn() }),
}))

import EmailGate from '@/components/EmailGate'
import CheckerResultsPage from '@/app/checker/[id]/page'
import { submitLead, getAnalysis, ApiError } from '@/lib/api'

const mockedSubmit = vi.mocked(submitLead)
const mockedGet = vi.mocked(getAnalysis)

describe('EmailGate component', () => {
  beforeEach(() => {
    mockedSubmit.mockReset()
  })

  it('has a labelled email input with a submit control', () => {
    render(<EmailGate submissionId="sub-1" hiddenCount={5} onUnlock={vi.fn()} />)
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /unlock full report/i }),
    ).toBeInTheDocument()
  })

  it('rejects an invalid email inline without posting or unlocking', async () => {
    const user = userEvent.setup()
    const onUnlock = vi.fn()
    render(<EmailGate submissionId="sub-1" hiddenCount={5} onUnlock={onUnlock} />)

    await user.type(screen.getByLabelText(/email/i), 'not-an-email')
    await user.click(screen.getByRole('button', { name: /unlock full report/i }))

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(mockedSubmit).not.toHaveBeenCalled()
    expect(onUnlock).not.toHaveBeenCalled()
  })

  it('posts a valid email and unlocks on success', async () => {
    const user = userEvent.setup()
    const onUnlock = vi.fn()
    mockedSubmit.mockResolvedValue(undefined)
    render(<EmailGate submissionId="sub-1" hiddenCount={5} onUnlock={onUnlock} />)

    await user.type(screen.getByLabelText(/email/i), 'buyer@example.com')
    await user.click(screen.getByRole('button', { name: /unlock full report/i }))

    await waitFor(() =>
      expect(mockedSubmit).toHaveBeenCalledWith('sub-1', 'buyer@example.com'),
    )
    expect(onUnlock).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('trims surrounding whitespace before posting', async () => {
    const user = userEvent.setup()
    mockedSubmit.mockResolvedValue(undefined)
    render(<EmailGate submissionId="sub-1" hiddenCount={5} onUnlock={vi.fn()} />)

    await user.type(screen.getByLabelText(/email/i), '  buyer@example.com  ')
    await user.click(screen.getByRole('button', { name: /unlock full report/i }))

    await waitFor(() =>
      expect(mockedSubmit).toHaveBeenCalledWith('sub-1', 'buyer@example.com'),
    )
  })

  it('shows an inline server error without unlocking', async () => {
    const user = userEvent.setup()
    const onUnlock = vi.fn()
    mockedSubmit.mockRejectedValue(new ApiError('Something broke.', 500))
    render(<EmailGate submissionId="sub-1" hiddenCount={5} onUnlock={onUnlock} />)

    await user.type(screen.getByLabelText(/email/i), 'buyer@example.com')
    await user.click(screen.getByRole('button', { name: /unlock full report/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/something broke/i)
    expect(onUnlock).not.toHaveBeenCalled()
  })

  it('blocks submit and warns when the submission id is missing', async () => {
    const user = userEvent.setup()
    const onUnlock = vi.fn()
    render(<EmailGate submissionId={null} hiddenCount={5} onUnlock={onUnlock} />)

    await user.type(screen.getByLabelText(/email/i), 'buyer@example.com')
    await user.click(screen.getByRole('button', { name: /unlock full report/i }))

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(mockedSubmit).not.toHaveBeenCalled()
    expect(onUnlock).not.toHaveBeenCalled()
  })

  it('is keyboard operable end to end', async () => {
    const user = userEvent.setup()
    mockedSubmit.mockResolvedValue(undefined)
    render(<EmailGate submissionId="sub-1" hiddenCount={5} onUnlock={vi.fn()} />)

    await user.tab()
    expect(screen.getByLabelText(/email/i)).toHaveFocus()
    await user.keyboard('buyer@example.com')
    await user.tab()
    expect(
      screen.getByRole('button', { name: /unlock full report/i }),
    ).toHaveFocus()
    await user.keyboard('{Enter}')

    await waitFor(() =>
      expect(mockedSubmit).toHaveBeenCalledWith('sub-1', 'buyer@example.com'),
    )
  })
})

// Locked responses envelope: eight answers, only the 5th mentions the brand.
function makeAnalysis(responses: Analysis['result']['responses']): Analysis {
  return {
    id: 'check-id',
    url: 'checker:Notion',
    status: 'done',
    current_step: null,
    progress: 100,
    error: null,
    created_at: '2026-07-10T00:00:00Z',
    updated_at: '2026-07-10T00:00:00Z',
    result: {
      footprint_count: 1,
      geo_score: 33,
      kyc: null,
      prompts: [{ id: 'p1', category: 'comparison', text: 'Best note app?' }],
      responses,
      total_responses: responses.length,
      engine_presence: null,
      competitors_appeared: null,
      serp: null,
      seo: null,
    },
  }
}

function response(
  id: string,
  footprint: boolean | null,
  raw: string,
): Analysis['result']['responses'][number] {
  return {
    id,
    engine: 'openai',
    model: 'gpt-4o-mini',
    footprint,
    matched_snippet: footprint ? 'Notion is a strong option.' : null,
    prompt_id: 'p1',
    raw_text: raw,
    cost_usd: 0.001,
  }
}

describe('checker results email gate wiring', () => {
  beforeEach(() => {
    mockedGet.mockReset()
    mockedSubmit.mockReset()
  })

  it('shows one free answer (the first that mentions the brand) and gates the rest', async () => {
    mockedGet.mockResolvedValue(
      makeAnalysis([
        response('r1', false, 'FIRST unrelated answer.'),
        response('r2', false, 'SECOND unrelated answer.'),
        response('r3', true, 'THIRD names the brand.'),
      ]),
    )
    render(<CheckerResultsPage />)

    await screen.findByRole('img') // ScoreGauge — done screen rendered
    // Exactly one answer row is present pre-email (one toggle button).
    expect(
      screen.getAllByRole('button', { name: /show full answer/i }),
    ).toHaveLength(1)
    expect(
      screen.getByRole('button', { name: /unlock full report/i }),
    ).toBeInTheDocument()

    // The free row is the brand-mentioning one, and it exposes that raw answer.
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /show full answer/i }))
    expect(screen.getByText('THIRD names the brand.')).toBeInTheDocument()
    expect(screen.queryByText('FIRST unrelated answer.')).not.toBeInTheDocument()
  })

  it('falls back to the first answer when none mentions the brand', async () => {
    mockedGet.mockResolvedValue(
      makeAnalysis([
        response('r1', false, 'FIRST unrelated answer.'),
        response('r2', false, 'SECOND unrelated answer.'),
        response('r3', null, 'THIRD unrelated answer.'),
      ]),
    )
    render(<CheckerResultsPage />)

    await screen.findByRole('img')
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /show full answer/i }))
    expect(screen.getByText('FIRST unrelated answer.')).toBeInTheDocument()
    expect(screen.queryByText('SECOND unrelated answer.')).not.toBeInTheDocument()
  })

  it('reveals every answer in place after a valid email', async () => {
    mockedSubmit.mockResolvedValue(undefined)
    mockedGet.mockResolvedValue(
      makeAnalysis([
        response('r1', true, 'FIRST names the brand.'),
        response('r2', false, 'SECOND unrelated answer.'),
        response('r3', false, 'THIRD unrelated answer.'),
      ]),
    )
    render(<CheckerResultsPage />)

    await screen.findByRole('img')
    expect(
      screen.getAllByRole('button', { name: /show full answer/i }),
    ).toHaveLength(1)

    const user = userEvent.setup()
    await user.type(screen.getByLabelText(/email/i), 'buyer@example.com')
    await user.click(screen.getByRole('button', { name: /unlock full report/i }))

    await waitFor(() =>
      expect(mockedSubmit).toHaveBeenCalledWith('sub-1', 'buyer@example.com'),
    )
    // All three answers are now present, and the gate is gone.
    await waitFor(() =>
      expect(
        screen.getAllByRole('button', { name: /show full answer/i }),
      ).toHaveLength(3),
    )
    expect(
      screen.queryByRole('button', { name: /unlock full report/i }),
    ).not.toBeInTheDocument()
  })
})
