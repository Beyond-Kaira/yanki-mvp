import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import NewAnalysisButton from '@/components/ai-visibility/NewAnalysisButton'

const push = vi.fn()
const clearBinding = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
}))

vi.mock('@/components/ai-visibility/useAnalysisBinding', () => ({
  useAnalysisBinding: () => ({ clearBinding }),
}))

vi.mock('@/components/ai-visibility/useUserAnalysisQuota', () => ({
  useUserAnalysisQuota: vi.fn(),
}))

import { useUserAnalysisQuota } from '@/components/ai-visibility/useUserAnalysisQuota'

const mockedQuota = vi.mocked(useUserAnalysisQuota)

beforeEach(() => {
  push.mockReset()
  clearBinding.mockReset()
  mockedQuota.mockReset()
})

describe('NewAnalysisButton', () => {
  it('clears the remembered analysis and opens the empty overview', async () => {
    mockedQuota.mockReturnValue({
      quota: { used: 1, limit: 5 },
      loading: false,
      error: null,
      atLimit: false,
      refresh: vi.fn(),
    })

    render(<NewAnalysisButton />)

    await userEvent.click(screen.getByRole('button', { name: 'New analysis' }))

    expect(clearBinding).toHaveBeenCalled()
    expect(push).toHaveBeenCalledWith('/ai-visibility')
  })

  it('is disabled at the user analysis stock limit', async () => {
    mockedQuota.mockReturnValue({
      quota: { used: 5, limit: 5 },
      loading: false,
      error: null,
      atLimit: true,
      refresh: vi.fn(),
    })

    render(<NewAnalysisButton />)

    const button = screen.getByRole('button', { name: 'New analysis' })
    expect(button).toBeDisabled()
    expect(screen.getByRole('status')).toHaveTextContent(/limit of 5 active analyses/i)
    expect(screen.getByRole('link', { name: /open your analyses/i })).toHaveAttribute(
      'href',
      '/analyses',
    )

    await userEvent.click(button)
    expect(clearBinding).not.toHaveBeenCalled()
    expect(push).not.toHaveBeenCalled()
  })
})
