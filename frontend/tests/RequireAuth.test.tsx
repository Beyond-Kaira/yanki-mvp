import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import RequireAuth from '@/components/RequireAuth'

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

function renderGuard() {
  return render(
    <RequireAuth>
      <p>protected content</p>
    </RequireAuth>,
  )
}

describe('RequireAuth', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.history.replaceState({}, '', '/')
  })

  it('renders nothing protected while the session is still resolving', () => {
    authState = { status: 'loading' }
    renderGuard()

    expect(screen.queryByText('protected content')).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent(/checking your session/i)
  })

  it('does NOT redirect while loading', () => {
    // The bug this prevents: bouncing to /login during a cold load, which signs
    // the user out on every page refresh.
    authState = { status: 'loading' }
    renderGuard()

    expect(replace).not.toHaveBeenCalled()
  })

  it('renders the content once authenticated', () => {
    authState = { status: 'authenticated' }
    renderGuard()

    expect(screen.getByText('protected content')).toBeVisible()
  })

  it('sends an anonymous visitor to login and never shows the content', async () => {
    authState = { status: 'anonymous' }
    window.history.replaceState({}, '', '/admin')
    renderGuard()

    expect(screen.queryByText('protected content')).not.toBeInTheDocument()
    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith(`/login?next=${encodeURIComponent('/admin')}`),
    )
  })

  it('carries the query string so the destination survives the round trip', async () => {
    authState = { status: 'anonymous' }
    window.history.replaceState({}, '', '/ai-visibility?analysis=abc123')
    renderGuard()

    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith(
        `/login?next=${encodeURIComponent('/ai-visibility?analysis=abc123')}`,
      ),
    )
  })
})
