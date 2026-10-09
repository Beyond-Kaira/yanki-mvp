import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import StartAnalysisPanel from '@/components/shell/StartAnalysisPanel'

vi.mock('@/components/ai-visibility/useUserAnalysisQuota', () => ({
  useUserAnalysisQuota: vi.fn(),
}))

vi.mock('@/components/UrlForm', () => ({
  default: ({ disabled }: { disabled: boolean }) => <button disabled={disabled}>UrlForm</button>,
}))

import { useUserAnalysisQuota } from '@/components/ai-visibility/useUserAnalysisQuota'

const mockedQuota = vi.mocked(useUserAnalysisQuota)

beforeEach(() => {
  mockedQuota.mockReset()
})

describe('StartAnalysisPanel', () => {
  it('keeps the form in place and disables it when the stock limit is full', () => {
    mockedQuota.mockReturnValue({
      quota: { used: 5, limit: 5 },
      loading: false,
      error: null,
      atLimit: true,
      refresh: vi.fn(),
    })

    render(<StartAnalysisPanel />)

    expect(screen.getByText(/5 \/ 5/)).toBeInTheDocument()
    expect(screen.getByText(/analyses active/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'UrlForm' })).toBeDisabled()
    expect(screen.getByRole('link', { name: /open your analyses/i })).toHaveAttribute(
      'href',
      '/analyses',
    )
  })

  it('shows the form when quota remains', () => {
    mockedQuota.mockReturnValue({
      quota: { used: 2, limit: 5 },
      loading: false,
      error: null,
      atLimit: false,
      refresh: vi.fn(),
    })

    render(<StartAnalysisPanel />)

    expect(screen.getByText('UrlForm')).toBeInTheDocument()
  })

  it('keeps the quota visible while a refresh is in flight', () => {
    mockedQuota.mockReturnValue({ quota: { used: 3, limit: 5 }, loading: true, error: null, atLimit: false, refresh: vi.fn() })
    render(<StartAnalysisPanel />)
    expect(screen.getByText(/3 \/ 5/)).toBeVisible()
  })
})
