import { render, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import RedirectIfAuthenticated from '@/components/RedirectIfAuthenticated'

const replace = vi.fn()
let authState: { status: 'loading' | 'authenticated' | 'anonymous' } = {
  status: 'loading',
}

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
}))

vi.mock('@/components/AuthProvider', () => ({
  useAuth: () => authState,
}))

describe('RedirectIfAuthenticated', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders nothing', () => {
    authState = { status: 'anonymous' }
    const { container } = render(<RedirectIfAuthenticated />)

    expect(container).toBeEmptyDOMElement()
  })

  it('does not redirect while the session is still resolving', () => {
    authState = { status: 'loading' }
    render(<RedirectIfAuthenticated />)

    expect(replace).not.toHaveBeenCalled()
  })

  it('does not redirect an anonymous visitor', () => {
    authState = { status: 'anonymous' }
    render(<RedirectIfAuthenticated />)

    expect(replace).not.toHaveBeenCalled()
  })

  it('sends a signed-in visitor to the dashboard', async () => {
    authState = { status: 'authenticated' }
    render(<RedirectIfAuthenticated />)

    await waitFor(() => expect(replace).toHaveBeenCalledWith('/dashboard'))
  })

  it('honours an explicit destination', async () => {
    authState = { status: 'authenticated' }
    render(<RedirectIfAuthenticated to="/settings" />)

    await waitFor(() => expect(replace).toHaveBeenCalledWith('/settings'))
  })
})
