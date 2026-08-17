import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import StartAnalysisPanel from '@/components/shell/StartAnalysisPanel'

vi.mock('@/components/ai-visibility/useUserAnalysisQuota', () => ({
  useUserAnalysisQuota: vi.fn(),
}))

vi.mock('@/components/UrlForm', () => ({
  default: () => <div>UrlForm</div>,
}))

import { useUserAnalysisQuota } from '@/components/ai-visibility/useUserAnalysisQuota'

const mockedQuota = vi.mocked(useUserAnalysisQuota)

beforeEach(() => {
  mockedQuota.mockReset()
})

describe('StartAnalysisPanel', () => {
  it('shows the quota chip and hides the form when the stock limit is full', () => {
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
    expect(screen.queryByText('UrlForm')).not.toBeInTheDocument()
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
})
