import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const push = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  // Auth screens still use SiteHeader; product routes hide it.
  usePathname: () => '/login',
}))

vi.mock('@/lib/auth', () => ({
  login: vi.fn(),
  signup: vi.fn(),
  logout: vi.fn(),
  fetchCurrentUser: vi.fn(),
  requestPasswordReset: vi.fn(),
  // The pages branch on this class, so the mock has to carry the real shape.
  SignedUpButNotSignedInError: class SignedUpButNotSignedInError extends Error {},
}))

vi.mock('@/lib/session', () => ({
  refreshAccessToken: vi.fn(),
  setAccessToken: vi.fn(),
  getAccessToken: vi.fn(() => null),
}))

import AuthProvider, { useAuth } from '@/components/AuthProvider'
import SiteHeader from '@/components/SiteHeader'
import { fetchCurrentUser, logout } from '@/lib/auth'
import { refreshAccessToken } from '@/lib/session'

// The header renders the same anonymous chrome for 'anonymous' and for a broken
// 'authenticated' with no user, so reading it back cannot tell the two apart.
// This reports the status itself.
function AuthStatusProbe() {
  const { status } = useAuth()
  return <output data-testid="auth-status">{status}</output>
}

const mockedRefresh = vi.mocked(refreshAccessToken)
const mockedMe = vi.mocked(fetchCurrentUser)
const mockedLogout = vi.mocked(logout)

const USER = {
  id: '11111111-1111-1111-1111-111111111111',
  email: 'ada@example.com',
  created_at: '2026-07-29T00:00:00Z',
}

function renderHeader() {
  return render(
    <AuthProvider>
      <SiteHeader />
    </AuthProvider>,
  )
}

describe('SiteHeader', () => {
  beforeEach(() => {
    push.mockReset()
    mockedRefresh.mockReset()
    mockedMe.mockReset()
    mockedLogout.mockReset()
  })

  it('offers the way in when there is no session', async () => {
    mockedRefresh.mockResolvedValue(null)
    renderHeader()

    expect(await screen.findByRole('link', { name: 'Sign up' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Login' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /log out/i })).not.toBeInTheDocument()
  })

  it('restores the session from the refresh cookie on load', async () => {
    mockedRefresh.mockResolvedValue('tok')
    mockedMe.mockResolvedValue(USER)
    renderHeader()

    expect(await screen.findByText('ada@example.com')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /log out/i })).toBeInTheDocument()
    // The signed-out pair is gone: the header agrees with the session.
    expect(screen.queryByRole('link', { name: 'Login' })).not.toBeInTheDocument()
  })

  it('shows neither state while the session is still unknown', () => {
    // A refresh that has not settled: rendering the signed-out pair here would
    // flash the wrong answer at someone who is in fact signed in.
    mockedRefresh.mockReturnValue(new Promise(() => {}))
    renderHeader()

    expect(screen.queryByRole('link', { name: 'Login' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /log out/i })).not.toBeInTheDocument()
    // Logo stays while auth state is unknown.
    expect(screen.getByRole('link', { name: 'Yanki' })).toBeInTheDocument()
  })

  it('signs out and returns home', async () => {
    const user = userEvent.setup()
    mockedRefresh.mockResolvedValue('tok')
    mockedMe.mockResolvedValue(USER)
    mockedLogout.mockResolvedValue(undefined)
    renderHeader()

    await user.click(await screen.findByRole('button', { name: /log out/i }))

    await waitFor(() => expect(mockedLogout).toHaveBeenCalled())
    expect(push).toHaveBeenCalledWith('/')
    expect(await screen.findByRole('link', { name: 'Login' })).toBeInTheDocument()
  })

  it('signs out locally even when the request fails', async () => {
    const user = userEvent.setup()
    mockedRefresh.mockResolvedValue('tok')
    mockedMe.mockResolvedValue(USER)
    mockedLogout.mockRejectedValue(new Error('network down'))
    renderHeader()

    await user.click(await screen.findByRole('button', { name: /log out/i }))

    // The token is gone either way, so a header still showing the account would
    // be lying about the state of the session.
    expect(await screen.findByRole('link', { name: 'Login' })).toBeInTheDocument()
    expect(screen.queryByText('ada@example.com')).not.toBeInTheDocument()
  })

  it('stays anonymous when the token cannot be spent', async () => {
    // A refresh that hands back a token the API then rejects is not a session.
    mockedRefresh.mockResolvedValue('tok')
    mockedMe.mockResolvedValue(null)
    render(
      <AuthProvider>
        <SiteHeader />
        <AuthStatusProbe />
      </AuthProvider>,
    )

    // Asserting the status, not the chrome: with a null user the header shows
    // the signed-out links whether the provider settled on 'anonymous' or
    // wrongly on 'authenticated', so only this distinguishes them.
    await waitFor(() =>
      expect(screen.getByTestId('auth-status')).toHaveTextContent('anonymous'),
    )
    expect(screen.getByRole('link', { name: 'Login' })).toBeInTheDocument()
  })
})
