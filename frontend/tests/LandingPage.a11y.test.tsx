import { render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import LandingPage from '@/app/page'
import { axeCheck } from './a11y'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}))

vi.mock('@/components/AuthProvider', () => ({
  useAuth: () => ({ status: 'anonymous' }),
}))

describe('Landing page accessibility', () => {
  it('has no axe violations', async () => {
    const { container } = render(<LandingPage />)
    expect(await axeCheck(container)).toHaveNoViolations()
  })
})
