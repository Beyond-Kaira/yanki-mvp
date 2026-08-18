import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import RecentAnalysesPanel from '@/components/ai-visibility/RecentAnalysesPanel'

const listAnalyses = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listAnalyses: (...args: unknown[]) => listAnalyses(...args),
  }
})

beforeEach(() => {
  listAnalyses.mockReset()
})

describe('RecentAnalysesPanel', () => {
  it('links each row into AI Visibility with the analysis id', async () => {
    listAnalyses.mockResolvedValue({
      total: 1,
      limit: 5,
      offset: 0,
      user_analyses_used: 1,
      user_analyses_limit: 5,
      analyses: [
        {
          id: 'an-1',
          url: 'https://acme.test/',
          status: 'done',
          progress: 100,
          current_step: null,
          error: null,
          geo_score: 55,
          total_responses: 8,
          created_at: '2026-08-09T09:00:00Z',
          updated_at: '2026-08-09T09:04:00Z',
        },
      ],
    })

    render(<RecentAnalysesPanel />)

    expect(await screen.findByRole('link', { name: /acme\.test/i })).toHaveAttribute(
      'href',
      '/ai-visibility?analysis=an-1',
    )
  })

  it('renders nothing when the history is empty', async () => {
    listAnalyses.mockResolvedValue({
      total: 0,
      limit: 5,
      offset: 0,
      user_analyses_used: 0,
      user_analyses_limit: 5,
      analyses: [],
    })

    const { container } = render(<RecentAnalysesPanel />)

    await waitFor(() => expect(listAnalyses).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })
})
