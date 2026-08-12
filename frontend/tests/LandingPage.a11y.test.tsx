import { render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import LandingPage from '@/app/page'
import { axeCheck } from './a11y'

let authState: { status: 'loading' | 'authenticated' | 'anonymous' } = {
  status: 'anonymous',
}

vi.mock('@/components/AuthProvider', () => ({
  useAuth: () => authState,
}))

describe('Landing page accessibility', () => {
  it('has no axe violations for a visitor', async () => {
    authState = { status: 'anonymous' }
    const { container } = render(<LandingPage />)
    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('has no axe violations for a signed-in reader', async () => {
    authState = { status: 'authenticated' }
    const { container } = render(<LandingPage />)
    expect(await axeCheck(container)).toHaveNoViolations()
  })
})
