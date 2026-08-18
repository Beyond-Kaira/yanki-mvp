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

beforeEach(() => {
  push.mockReset()
  clearBinding.mockReset()
})

describe('NewAnalysisButton', () => {
  it('clears the remembered analysis and opens the empty overview', async () => {
    render(<NewAnalysisButton />)

    await userEvent.click(screen.getByRole('button', { name: 'New analysis' }))

    expect(clearBinding).toHaveBeenCalled()
    expect(push).toHaveBeenCalledWith('/ai-visibility')
  })
})
