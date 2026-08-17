import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AnalysisHistoryClient from '@/app/analyses/AnalysisHistoryClient'
import { ApiError } from '@/lib/api'

const listAnalyses = vi.fn()
const deleteAnalysis = vi.fn()
const clearBinding = vi.fn()
const notifyQuotaChanged = vi.fn()

vi.mock('@/components/ai-visibility/useAnalysisBinding', () => ({
  useAnalysisBinding: () => ({ clearBinding, notifyQuotaChanged }),
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listAnalyses: (...args: unknown[]) => listAnalyses(...args),
    deleteAnalysis: (...args: unknown[]) => deleteAnalysis(...args),
  }
})

function row(overrides: Record<string, unknown> = {}) {
  return {
    id: 'an-1',
    url: 'https://acme.test/',
    status: 'done',
    progress: 100,
    current_step: null,
    error: null,
    geo_score: 61.5,
    total_responses: 12,
    created_at: '2026-08-09T09:00:00Z',
    updated_at: '2026-08-09T09:04:00Z',
    ...overrides,
  }
}

function page(rows: Record<string, unknown>[], total = rows.length, offset = 0) {
  return {
    total,
    limit: 20,
    offset,
    analyses: rows,
    user_analyses_used: rows.length,
    user_analyses_limit: 5,
  }
}

beforeEach(() => {
  listAnalyses.mockReset()
  deleteAnalysis.mockReset()
  clearBinding.mockReset()
  notifyQuotaChanged.mockReset()
})

describe('Analysis history', () => {
  it('lists the organization runs with a link back to each result', async () => {
    listAnalyses.mockResolvedValue(page([row(), row({ id: 'an-2', url: 'https://beta.test' })]))

    render(<AnalysisHistoryClient />)

    const table = await screen.findByRole('table')
    expect(within(table).getByRole('link', { name: 'acme.test' })).toHaveAttribute(
      'href',
      '/analyses/an-1',
    )
    expect(within(table).getByRole('link', { name: 'beta.test' })).toHaveAttribute(
      'href',
      '/analyses/an-2',
    )
  })

  it('renders a missing score as an em dash, never a zero', async () => {
    // The rule this screen must never relax. A queued run has not been
    // measured; rendering `null` as `0` would tell a customer their brand is
    // invisible when the truth is that nobody has looked yet.
    listAnalyses.mockResolvedValue(
      page([row({ status: 'queued', progress: 0, geo_score: null })]),
    )

    render(<AnalysisHistoryClient />)

    const table = await screen.findByRole('table')
    expect(within(table).getByText('—')).toBeInTheDocument()
    expect(within(table).queryByText('0.0')).not.toBeInTheDocument()
  })

  it('still shows a real zero as a zero', async () => {
    // The other half of the same rule: suppressing a genuine 0.0 would be the
    // mirror-image lie.
    listAnalyses.mockResolvedValue(page([row({ geo_score: 0 })]))

    render(<AnalysisHistoryClient />)

    const table = await screen.findByRole('table')
    expect(within(table).getByText('0.0')).toBeInTheDocument()
  })

  it('reports the total from the server rather than the rows on screen', async () => {
    listAnalyses.mockResolvedValue(page([row()], 47))

    render(<AnalysisHistoryClient />)

    expect(await screen.findByText('Showing 1–20 of 47')).toBeInTheDocument()
  })

  it('asks the server for the next page instead of slicing locally', async () => {
    listAnalyses.mockResolvedValue(page([row()], 47))
    render(<AnalysisHistoryClient />)
    await screen.findByRole('table')

    await userEvent.click(screen.getByRole('button', { name: 'Next' }))

    await waitFor(() =>
      expect(listAnalyses).toHaveBeenLastCalledWith(
        expect.objectContaining({ offset: 20, limit: 20 }),
        expect.anything(),
      ),
    )
  })

  it('sends the status filter and resets to the first page', async () => {
    listAnalyses.mockResolvedValue(page([row()], 47))
    render(<AnalysisHistoryClient />)
    await screen.findByRole('table')
    await userEvent.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => expect(listAnalyses).toHaveBeenCalledTimes(2))

    await userEvent.click(screen.getByRole('button', { name: 'Failed' }))

    // Offset back to 0: staying on page 3 of a filter that matches four rows
    // shows an empty table and reads as "no results".
    await waitFor(() =>
      expect(listAnalyses).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: 'failed', offset: 0 }),
        expect.anything(),
      ),
    )
  })

  it('offers a way to start one when the history is empty', async () => {
    listAnalyses.mockResolvedValue(page([]))

    render(<AnalysisHistoryClient />)

    expect(await screen.findByText('No analyses yet.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Start an analysis' })).toHaveAttribute(
      'href',
      '/dashboard',
    )
  })

  it('does not offer to start one when a filter is what emptied the list', async () => {
    listAnalyses.mockResolvedValue(page([row()], 1))
    render(<AnalysisHistoryClient />)
    await screen.findByRole('table')

    listAnalyses.mockResolvedValue(page([]))
    await userEvent.click(screen.getByRole('button', { name: 'Failed' }))

    expect(await screen.findByText('No analyses with that status yet.')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Start an analysis' })).not.toBeInTheDocument()
  })

  it('surfaces the API message when the session has expired', async () => {
    listAnalyses.mockRejectedValue(
      new ApiError('Your session has expired. Sign in again to see your analyses.', 401),
    )

    render(<AnalysisHistoryClient />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Your session has expired')
  })

  it('shows the failure reason on a failed run', async () => {
    listAnalyses.mockResolvedValue(
      page([row({ status: 'failed', geo_score: null, error: 'discovery timed out' })]),
    )

    render(<AnalysisHistoryClient />)

    expect(await screen.findByText('discovery timed out')).toBeInTheDocument()
  })

  it('deletes a finished run and reloads the list', async () => {
    listAnalyses.mockResolvedValue(page([row()]))
    deleteAnalysis.mockResolvedValue(undefined)
    vi.stubGlobal('confirm', vi.fn(() => true))

    render(<AnalysisHistoryClient />)
    await screen.findByRole('table')

    await userEvent.click(
      screen.getByRole('button', { name: 'Delete analysis for acme.test' }),
    )

    await waitFor(() => expect(deleteAnalysis).toHaveBeenCalledWith('an-1'))
    expect(clearBinding).toHaveBeenCalledWith('an-1')
    expect(notifyQuotaChanged).toHaveBeenCalled()
    await waitFor(() => expect(listAnalyses).toHaveBeenCalledTimes(2))
    vi.unstubAllGlobals()
  })

  it('offers delete only on finished runs', async () => {
    listAnalyses.mockResolvedValue(
      page([row({ status: 'running', progress: 40 }), row({ id: 'an-2', status: 'done' })]),
    )

    render(<AnalysisHistoryClient />)

    const table = await screen.findByRole('table')
    expect(
      within(table).getAllByRole('button', { name: 'Delete analysis for acme.test' }),
    ).toHaveLength(1)
  })
})
