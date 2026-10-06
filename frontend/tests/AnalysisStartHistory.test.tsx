import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AnalysisSummary } from '@/lib/contracts'
import { ANALYSES_POLL_MS } from '@/components/ai-visibility/useAnalysesList'

const { push, createAnalysis, listAnalyses, getAnalysis, identity } = vi.hoisted(() => ({
  push: vi.fn(), createAnalysis: vi.fn(), listAnalyses: vi.fn(), getAnalysis: vi.fn(),
  identity: { user: { id: 'user-1', organization: { id: 'org-1' } } },
}))
vi.mock('next/navigation', () => ({
  usePathname: () => '/ai-visibility', useRouter: () => ({ push }),
}))
vi.mock('@/components/AuthProvider', () => ({
  useAuth: () => identity,
}))
vi.mock('@/components/ai-visibility/useAnalysisQuery', () => ({
  useAnalysisQuery: () => ({ status: 'empty', analysis: null }),
}))
vi.mock('@/components/ai-visibility/useUserAnalysisQuota', () => ({
  useUserAnalysisQuota: () => ({ quota: { used: 2, limit: 5 }, loading: false, atLimit: false }),
}))
vi.mock('@/lib/api', async (original) => ({ ...(await original<typeof import('@/lib/api')>()), createAnalysis, listAnalyses, getAnalysis }))

import OverviewClient from '@/app/ai-visibility/OverviewClient'
import AnalysisSessionProvider from '@/components/AnalysisSessionProvider'
import { notifyAnalysisQuotaChanged } from '@/lib/analysis-quota-events'

const finished: AnalysisSummary = {
  id: 'finished', url: 'https://finished.test/', status: 'done', current_step: null, progress: 100,
  geo_score: 61.5, created_at: '2026-10-06T09:00:00Z', updated_at: '2026-10-06T09:03:00Z', error: null,
}
const live: AnalysisSummary = {
  ...finished, id: 'new-run', url: 'https://acme.test/', status: 'running', progress: 45, current_step: 'execute', geo_score: null,
}
const historyPage = (analyses: AnalysisSummary[]) => ({ analyses, total: analyses.length, user_analyses_used: analyses.length, user_analyses_limit: 5, limit: 5, offset: 0 })

const renderOverview = () => render(<AnalysisSessionProvider><OverviewClient /></AnalysisSessionProvider>)
beforeEach(() => {
  vi.resetAllMocks()
  sessionStorage.clear()
  identity.user = { id: 'user-1', organization: { id: 'org-1' } }
  getAnalysis.mockResolvedValue(live)
})
afterEach(() => { vi.useRealTimers() })

describe('start form with live history', () => {
  it('keeps the form and finished runs visible from submission through completion', async () => {
    let rows = [finished]
    listAnalyses.mockImplementation(async () => historyPage(rows))
    createAnalysis.mockImplementation(async () => { rows = [live, finished]; return { id: live.id } })
    renderOverview()
    await screen.findByRole('link', { name: /finished\.test/i })
    const url = screen.getByRole('textbox', { name: /url/i })
    await userEvent.type(url, live.url)
    await userEvent.click(screen.getByRole('button', { name: 'Run analysis' }))
    const card = await screen.findByRole('article', { name: 'Analysis for acme.test' })
    expect(push).toHaveBeenCalledWith('/ai-visibility')
    expect(sessionStorage.getItem('yanki:lastAnalysisId')).toBe(live.id)
    expect(screen.getByRole('textbox', { name: /url/i })).toBe(url)
    expect(screen.getByRole('button', { name: 'Run analysis' })).toBeEnabled()
    expect(screen.getByRole('link', { name: /finished\.test/i })).toBeVisible()
    expect(within(card).getByRole('progressbar')).toHaveAttribute('aria-valuenow', '45')
    rows = [{ ...live, status: 'done', progress: 100, current_step: null, geo_score: 72 }, finished]
    await act(async () => { notifyAnalysisQuotaChanged() })
    expect(await screen.findByRole('link', { name: /acme\.test/i })).toHaveAttribute('href', '/ai-visibility?analysis=new-run')
    expect(screen.queryByRole('article', { name: 'Analysis for acme.test' })).not.toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: /url/i })).toBe(url)
    expect(screen.getByText('Analysis for acme.test complete. Your results are ready.')).toHaveAttribute('aria-live', 'polite')
    expect(push).toHaveBeenCalledTimes(1)
  })

  it('updates live progress automatically and stops polling after completion', async () => {
    vi.useFakeTimers()
    listAnalyses.mockResolvedValueOnce(historyPage([live, finished]))
      .mockResolvedValue(historyPage([{ ...live, status: 'done', progress: 100, current_step: null, geo_score: 72 }, finished]))
    renderOverview()
    await act(async () => {})
    expect(screen.getByRole('progressbar')).toBeInTheDocument()
    await act(async () => { await vi.advanceTimersByTimeAsync(ANALYSES_POLL_MS) })
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /acme\.test/i })).toBeInTheDocument()
    const requests = listAnalyses.mock.calls.length
    await act(async () => { await vi.advanceTimersByTimeAsync(ANALYSES_POLL_MS * 3) })
    expect(listAnalyses).toHaveBeenCalledTimes(requests)
  })

  it('keeps a new job visible when the list omits it, including across a reload', async () => {
    listAnalyses.mockResolvedValue(historyPage([finished]))
    createAnalysis.mockResolvedValue({ id: live.id })
    const view = renderOverview()
    await screen.findByRole('link', { name: /finished\.test/i })
    await userEvent.type(screen.getByRole('textbox', { name: /url/i }), live.url)
    await userEvent.click(screen.getByRole('button', { name: 'Run analysis' }))
    await screen.findByRole('article', { name: 'Analysis for acme.test' })
    expect(await screen.findByRole('progressbar')).toHaveAttribute('aria-valuenow', '45')
    expect(getAnalysis).toHaveBeenCalledWith(live.id, expect.any(AbortSignal))
    expect(sessionStorage.getItem('yanki:pendingAnalyses:user-1:org-1')).toBe('["new-run"]')
    view.unmount()
    renderOverview()
    expect(await screen.findByRole('progressbar')).toHaveAttribute('aria-valuenow', '45')
    expect(screen.getByRole('link', { name: /finished\.test/i })).toBeVisible()
    getAnalysis.mockResolvedValue({ ...live, status: 'done', progress: 100, current_step: null })
    await act(async () => { notifyAnalysisQuotaChanged() })
    expect(await screen.findByRole('link', { name: /acme\.test/i })).toBeVisible()
    expect(sessionStorage.getItem('yanki:pendingAnalyses:user-1:org-1')).toBe('[]')
    // A later refresh must not erase a completed result while the list lags.
    await act(async () => { notifyAnalysisQuotaChanged() })
    expect(screen.getByRole('link', { name: /acme\.test/i })).toBeVisible()
  })

  it('retains a collapsed live card during omitted rows and network failures, then recovers', async () => {
    listAnalyses.mockResolvedValue(historyPage([live, finished]))
    renderOverview()
    const card = await screen.findByRole('article', { name: 'Analysis for acme.test' })
    await userEvent.click(within(card).getByRole('button', { name: /collapse analysis steps/i }))
    listAnalyses.mockResolvedValue(historyPage([finished]))
    getAnalysis.mockRejectedValue(new Error('Network unavailable'))
    await act(async () => { notifyAnalysisQuotaChanged() })
    expect(screen.getByRole('article', { name: 'Analysis for acme.test' })).toBe(card)
    expect(within(card).getByRole('button', { name: /show analysis steps/i })).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByRole('alert')).toHaveTextContent('Retrying automatically')
    getAnalysis.mockResolvedValue({ ...live, progress: 80, current_step: 'footprint' })
    await act(async () => { notifyAnalysisQuotaChanged() })
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '80')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(within(card).getByRole('button', { name: /show analysis steps/i })).toHaveAttribute('aria-expanded', 'false')
  })

  it('does not restore another user or workspace pending jobs', async () => {
    sessionStorage.setItem('yanki:pendingAnalyses:user-1:org-1', '["new-run"]')
    listAnalyses.mockResolvedValue(historyPage([]))
    identity.user = { id: 'user-2', organization: { id: 'org-1' } }
    const view = renderOverview()
    await act(async () => {})
    expect(getAnalysis).not.toHaveBeenCalled()
    identity.user = { id: 'user-1', organization: { id: 'org-2' } }
    view.rerender(<AnalysisSessionProvider><OverviewClient /></AnalysisSessionProvider>)
    await act(async () => {})
    expect(getAnalysis).not.toHaveBeenCalled()
    expect(screen.queryByRole('article')).not.toBeInTheDocument()
  })

  it('keeps a failed run visible with its reason rather than silently losing the card', async () => {
    listAnalyses.mockResolvedValue(historyPage([live, finished]))
    renderOverview()
    const card = await screen.findByRole('article', { name: 'Analysis for acme.test' })
    listAnalyses.mockResolvedValue(historyPage([{ ...live, status: 'failed', error: 'Discovery timed out.' }, finished]))
    await act(async () => { notifyAnalysisQuotaChanged() })
    expect(screen.getByRole('article', { name: 'Analysis for acme.test' })).toBe(card)
    expect(within(card).getByRole('alert')).toHaveTextContent('Discovery timed out.')
    expect(within(card).getByRole('link', { name: /view failure details/i })).toHaveAttribute('href', '/analyses/new-run')
    expect(screen.getByRole('button', { name: 'Run analysis' })).toBeEnabled()
  })
})
