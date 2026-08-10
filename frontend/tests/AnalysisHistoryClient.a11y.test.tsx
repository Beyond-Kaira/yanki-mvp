import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axeCheck } from './a11y'

const mockedListAnalyses = vi.hoisted(() => vi.fn())

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return { ...actual, listAnalyses: mockedListAnalyses }
})

import AnalysisHistoryClient from '@/app/analyses/AnalysisHistoryClient'

const ROW = {
  id: '4bb0f6e1-d873-47ce-b15a-d166c43f91f8',
  url: 'https://acme.test/',
  status: 'done',
  progress: 100,
  current_step: null,
  error: null,
  geo_score: 61.5,
  total_responses: 12,
  created_at: '2026-08-09T09:00:00Z',
  updated_at: '2026-08-09T09:04:00Z',
}

describe('Analysis history accessibility', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('has no axe violations with rows and pagination', async () => {
    mockedListAnalyses.mockResolvedValue({
      total: 47,
      limit: 20,
      offset: 0,
      analyses: [ROW],
    })
    const { container } = render(<AnalysisHistoryClient />)

    await screen.findByRole('table')
    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('has no axe violations in the empty state', async () => {
    mockedListAnalyses.mockResolvedValue({ total: 0, limit: 20, offset: 0, analyses: [] })
    const { container } = render(<AnalysisHistoryClient />)

    await screen.findByText('No analyses yet.')
    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('gives the table a caption, so a screen reader knows what it lists', async () => {
    mockedListAnalyses.mockResolvedValue({
      total: 1,
      limit: 20,
      offset: 0,
      analyses: [ROW],
    })
    render(<AnalysisHistoryClient />)

    const table = await screen.findByRole('table')
    expect(table).toHaveAccessibleName(/analyses, newest first/i)
  })
})
