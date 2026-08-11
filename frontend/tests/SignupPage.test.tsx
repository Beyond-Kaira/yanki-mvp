import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const push = vi.fn()

const replace = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace }),
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
  onSessionLost: vi.fn(() => () => {}),
}))

import AuthProvider from '@/components/AuthProvider'
import { SignedUpButNotSignedInError } from '@/lib/auth'
import SignupPage from '@/app/signup/page'
import { fetchCurrentUser, login, signup } from '@/lib/auth'
import { refreshAccessToken } from '@/lib/session'

const mockedSignup = vi.mocked(signup)
const mockedLogin = vi.mocked(login)
const mockedRefresh = vi.mocked(refreshAccessToken)

const USER = {
  id: '11111111-1111-1111-1111-111111111111',
  email: 'ada@example.com',
  created_at: '2026-07-29T00:00:00Z',
}

function renderPage() {
  return render(
    <AuthProvider>
      <SignupPage />
    </AuthProvider>,
  )
}

async function fillValidForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('Work email'), 'ada@example.com')
  await user.type(screen.getByLabelText('Password'), 'hunter2!pass')
  await user.type(screen.getByLabelText('Confirm password'), 'hunter2!pass')
}

describe('SignupPage', () => {
  beforeEach(() => {
    push.mockReset()
    replace.mockReset()
    vi.mocked(fetchCurrentUser).mockReset()
    mockedSignup.mockReset()
    mockedLogin.mockReset()
    mockedRefresh.mockReset().mockResolvedValue(null)
  })

  // Accessibility lives in SignupPage.a11y.test.tsx, beside the other nine.

  it('collects no name, because the account has no such field', () => {
    renderPage()
    // `SignupRequest` is {email, password} and the user row carries id, email
    // and created_at. An input here would gather something with nowhere to go.
    expect(screen.queryByLabelText(/name/i)).not.toBeInTheDocument()
  })

  it('reports every empty field at once and posts nothing', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(screen.getByRole('button', { name: 'Sign up' }))

    expect(screen.getByText('Enter your email address.')).toBeInTheDocument()
    expect(screen.getByText('Choose a password.')).toBeInTheDocument()
    expect(screen.getByText('Re-enter your password.')).toBeInTheDocument()
    expect(mockedSignup).not.toHaveBeenCalled()
  })

  it('rejects a password under the minimum the backend enforces', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.type(screen.getByLabelText('Password'), 'short')
    await user.click(screen.getByRole('button', { name: 'Sign up' }))

    expect(screen.getByText('Use at least 8 characters.')).toBeInTheDocument()
    expect(mockedSignup).not.toHaveBeenCalled()
  })

  it('rejects a confirmation that does not match', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.type(screen.getByLabelText('Password'), 'hunter2!pass')
    await user.type(screen.getByLabelText('Confirm password'), 'hunter2!different')
    await user.click(screen.getByRole('button', { name: 'Sign up' }))

    expect(screen.getByText('Passwords do not match.')).toBeInTheDocument()
    expect(mockedSignup).not.toHaveBeenCalled()
  })

  it('asks for no agreement, because there are no terms to agree to', () => {
    renderPage()
    // A required consent pointing at an unwritten document is not consent. The
    // checkbox belongs here only once /terms carries real text.
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /terms/i })).not.toBeInTheDocument()
  })

  it('signs in with the same credentials, since signup issues no session', async () => {
    const user = userEvent.setup()
    mockedSignup.mockResolvedValue(USER)
    mockedLogin.mockResolvedValue({ user: USER, accessToken: 'tok' })
    renderPage()

    await fillValidForm(user)
    await user.click(screen.getByRole('button', { name: 'Sign up' }))

    await waitFor(() =>
      expect(mockedSignup).toHaveBeenCalledWith({
        email: 'ada@example.com',
        password: 'hunter2!pass',
        // Individual is the default, and it is sent explicitly rather than
        // omitted so the request says what it means.
        account_type: 'individual',
        organization_name: null,
      }),
    )
    // Without this second call the new account would land back on the site
    // signed out, having just typed its password.
    expect(mockedLogin).toHaveBeenCalledWith({
      email: 'ada@example.com',
      password: 'hunter2!pass',
    })
    expect(push).toHaveBeenCalledWith('/dashboard')
    // The confirmation field is a client-side check and never leaves the page.
    expect(JSON.stringify(mockedSignup.mock.calls)).not.toMatch(/confirm/i)
  })

  it('surfaces a taken email and leaves the form usable', async () => {
    const user = userEvent.setup()
    mockedSignup.mockRejectedValue(
      new Error('An account with that email already exists.'),
    )
    renderPage()

    await fillValidForm(user)
    await user.click(screen.getByRole('button', { name: 'Sign up' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/already exists/i)
    expect(mockedLogin).not.toHaveBeenCalled()
    expect(push).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Sign up' })).toBeEnabled()
  })

  it('says the account exists when only the follow-up sign-in fails', async () => {
    const user = userEvent.setup()
    mockedSignup.mockResolvedValue(USER)
    mockedLogin.mockRejectedValue(new Error('Sign-in is unavailable right now.'))
    renderPage()

    await fillValidForm(user)
    await user.click(screen.getByRole('button', { name: 'Sign up' }))

    // Telling them it could not be created would send them back to a form that
    // now answers 409.
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/account was created/i)
    expect(alert).not.toHaveTextContent(/couldn't create/i)
    expect(push).not.toHaveBeenCalled()
  })

  it('sends someone already signed in away from the form', async () => {
    mockedRefresh.mockResolvedValue('tok')
    vi.mocked(fetchCurrentUser).mockResolvedValue(USER)
    render(
      <AuthProvider>
        <SignupPage />
      </AuthProvider>,
    )

    await waitFor(() => expect(replace).toHaveBeenCalledWith('/dashboard'))
  })

  it('blocks a second submit while the first is in flight', async () => {
    const user = userEvent.setup()
    mockedSignup.mockReturnValue(new Promise(() => {}))
    renderPage()

    await fillValidForm(user)
    const submit = screen.getByRole('button', { name: 'Sign up' })
    await user.click(submit)

    expect(submit).toBeDisabled()
    await user.click(submit)
    expect(mockedSignup).toHaveBeenCalledTimes(1)
  })

  it('shows the length rule as a hint, not as an error', () => {
    renderPage()

    const field = screen.getByLabelText('Password')
    expect(field).toHaveAttribute('aria-describedby', 'password-hint')
    expect(field).not.toHaveAttribute('aria-invalid')
  })

  it('offers both account types and defaults to individual', () => {
    renderPage()

    const individual = screen.getByRole('radio', { name: /individual/i })
    const organization = screen.getByRole('radio', { name: /organization/i })

    expect(individual).toBeChecked()
    expect(organization).not.toBeChecked()
    // The org-name field only exists once it is needed.
    expect(screen.queryByLabelText(/organization name/i)).not.toBeInTheDocument()
  })

  it('requires a name for an organization account and sends it', async () => {
    const user = userEvent.setup()
    mockedSignup.mockResolvedValue(USER)
    mockedLogin.mockResolvedValue({ user: USER, accessToken: 'tok' })
    renderPage()

    await user.click(screen.getByRole('radio', { name: /organization/i }))
    await fillValidForm(user)

    // Submitting with no organization name must not reach the API.
    await user.click(screen.getByRole('button', { name: 'Sign up' }))
    expect(mockedSignup).not.toHaveBeenCalled()
    expect(await screen.findByText(/enter your organization name/i)).toBeVisible()

    await user.type(screen.getByLabelText(/organization name/i), 'Acme Industries')
    await user.click(screen.getByRole('button', { name: 'Sign up' }))

    await waitFor(() =>
      expect(mockedSignup).toHaveBeenCalledWith({
        email: 'ada@example.com',
        password: 'hunter2!pass',
        account_type: 'organization',
        organization_name: 'Acme Industries',
      }),
    )
  })
})