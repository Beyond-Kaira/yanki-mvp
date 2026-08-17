import { renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { getAnalysis, setAnalysisId } = vi.hoisted(() => ({
  getAnalysis: vi.fn(),
  setAnalysisId: vi.fn(),
}))

let pathname = '/ai-visibility'
let search = ''

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(search),
  usePathname: () => pathname,
}))

vi.mock('@/components/AnalysisSessionProvider', () => ({
  useAnalysisSession: () => ({
    analysisId: 'remembered-in-session',
    setAnalysisId,
  }),
}))

vi.mock('@/components/ai-visibility/useAnalysisBinding', () => ({
  useAnalysisBinding: () => ({
    clearBinding: vi.fn(),
  }),
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getAnalysis,
    fetchAnalysisSlices: vi.fn(),
  }
})

import { useAnalysisQuery } from '@/components/ai-visibility/useAnalysisQuery'

beforeEach(() => {
  pathname = '/ai-visibility'
  search = ''
  getAnalysis.mockReset()
  setAnalysisId.mockReset()
})

describe('useAnalysisQuery', () => {
  it('does not load a remembered session id on overview without a query param', async () => {
    const { result } = renderHook(() => useAnalysisQuery())

    await waitFor(() => expect(result.current.status).toBe('empty'))

    expect(getAnalysis).not.toHaveBeenCalled()
    expect(result.current.analysisId).toBeNull()
  })

  it('loads a remembered session id on AI Visibility subpages', async () => {
    pathname = '/ai-visibility/prompts'
    getAnalysis.mockResolvedValue({
      id: 'remembered-in-session',
      status: 'done',
      url: 'https://acme.test',
    })

    const { result } = renderHook(() => useAnalysisQuery())

    await waitFor(() => expect(getAnalysis).toHaveBeenCalledWith('remembered-in-session'))

    expect(result.current.analysisId).toBe('remembered-in-session')
  })
})
