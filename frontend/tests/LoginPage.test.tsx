import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'

const push = vi.fn()
const replace = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace }),
  // The login form reads `?next` so the auth guard can return people to the
  // page they asked for.
  useSearchParams: () => new URLSearchParams(),
}))

// The network edge is mocked; the provider and the page are the real thing, so
// these exercise the wiring between them rather than a stand-in for it.
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
  onSessionLost: vi.fn(() => () => {}),
}))

import AuthProvider from '@/components/AuthProvider'
import LoginPage from '@/app/login/page'
import { fetchCurrentUser, login } from '@/lib/auth'
import { refreshAccessToken } from '@/lib/session'

const mockedLogin = vi.mocked(login)
const mockedRefresh = vi.mocked(refreshAccessToken)

const USER = {
  id: '11111111-1111-1111-1111-111111111111',
  email: 'ada@example.com',
  created_at: '2026-07-29T00:00:00Z',
}

function renderPage(ui: ReactNode = <LoginPage />) {
  return render(<AuthProvider>{ui}</AuthProvider>)
}

describe('LoginPage', () => {
  beforeEach(() => {
    push.mockReset()
    replace.mockReset()
    vi.mocked(fetchCurrentUser).mockReset()
    mockedLogin.mockReset()
    // No refresh cookie: the provider settles on anonymous.
    mockedRefresh.mockReset().mockResolvedValue(null)
  })

  // Accessibility lives in LoginPage.a11y.test.tsx, beside the other nine.

  it('reports each field under its own input and posts nothing', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(screen.getByRole('button', { name: 'Login' }))

    expect(screen.getByText('Enter your email address.')).toBeInTheDocument()
    expect(screen.getByText('Enter your password.')).toBeInTheDocument()
    expect(mockedLogin).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Email')).toHaveAttribute(
      'aria-describedby',
      'email-error',
    )
  })

  it('rejects a malformed address without calling the API', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.type(screen.getByLabelText('Email'), 'not-an-email')
    await user.type(screen.getByLabelText('Password'), 'hunter2!')
    await user.click(screen.getByRole('button', { name: 'Login' }))

    expect(screen.getByText('Enter a valid email address.')).toBeInTheDocument()
    expect(mockedLogin).not.toHaveBeenCalled()
  })

  it('sends just the credentials the endpoint takes, then redirects', async () => {
    const user = userEvent.setup()
    mockedLogin.mockResolvedValue({ user: USER, accessToken: 'tok' })
    renderPage()

    await user.type(screen.getByLabelText('Email'), '  ada@example.com  ')
    await user.type(screen.getByLabelText('Password'), 'hunter2!')
    await user.click(screen.getByRole('button', { name: 'Login' }))

    await waitFor(() =>
      expect(mockedLogin).toHaveBeenCalledWith({
        email: 'ada@example.com',
        password: 'hunter2!',
      }),
    )
    expect(push).toHaveBeenCalledWith('/dashboard')
  })

  it('surfaces an API failure and leaves the form usable', async () => {
    const user = userEvent.setup()
    mockedLogin.mockRejectedValue(
      new Error('That email and password do not match an account.'),
    )
    renderPage()

    await user.type(screen.getByLabelText('Email'), 'ada@example.com')
    await user.type(screen.getByLabelText('Password'), 'wrong-one')
    await user.click(screen.getByRole('button', { name: 'Login' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/do not match an account/i)
    expect(push).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Login' })).toBeEnabled()
  })

  it('blocks a second submit while the first is in flight', async () => {
    const user = userEvent.setup()
    mockedLogin.mockReturnValue(new Promise(() => {}))
    renderPage()

    await user.type(screen.getByLabelText('Email'), 'ada@example.com')
    await user.type(screen.getByLabelText('Password'), 'hunter2!')

    const submit = screen.getByRole('button', { name: 'Login' })
    await user.click(submit)

    expect(submit).toBeDisabled()
    await user.click(submit)
    expect(mockedLogin).toHaveBeenCalledTimes(1)
  })

  it('reveals and re-hides the password', async () => {
    const user = userEvent.setup()
    renderPage()

    const field = screen.getByLabelText('Password')
    expect(field).toHaveAttribute('type', 'password')

    await user.click(screen.getByRole('button', { name: /show password/i }))
    expect(field).toHaveAttribute('type', 'text')

    await user.click(screen.getByRole('button', { name: /hide password/i }))
    expect(field).toHaveAttribute('type', 'password')
  })

  it('sends someone already signed in away from the form', async () => {
    mockedRefresh.mockResolvedValue('tok')
    vi.mocked(fetchCurrentUser).mockResolvedValue(USER)
    renderPage()

    await waitFor(() => expect(replace).toHaveBeenCalledWith('/dashboard'))
  })

  it('offers no remember-me control, since the endpoint takes no such flag', () => {
    renderPage()
    // Session length is the refresh cookie's max_age, decided server-side.
    expect(screen.queryByLabelText(/remember me/i)).not.toBeInTheDocument()
  })
})
