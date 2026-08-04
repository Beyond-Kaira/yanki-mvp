import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axeCheck } from './a11y'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

vi.mock('@/lib/auth', () => ({
  login: vi.fn(),
  signup: vi.fn(),
  logout: vi.fn(),
  fetchCurrentUser: vi.fn(),
  requestPasswordReset: vi.fn(),
  SignedUpButNotSignedInError: class SignedUpButNotSignedInError extends Error {},
}))

vi.mock('@/lib/session', () => ({
  refreshAccessToken: vi.fn(),
  setAccessToken: vi.fn(),
  getAccessToken: vi.fn(() => null),
}))

import AuthProvider from '@/components/AuthProvider'
import LoginPage from '@/app/login/page'
import { login } from '@/lib/auth'
import { refreshAccessToken } from '@/lib/session'

function renderPage() {
  return render(
    <AuthProvider>
      <LoginPage />
    </AuthProvider>,
  )
}

describe('LoginPage accessibility', () => {
  beforeEach(() => {
    // No refresh cookie: the provider settles on anonymous.
    vi.mocked(refreshAccessToken).mockReset().mockResolvedValue(null)
    vi.mocked(login).mockReset()
  })

  it('has no axe violations on the default render', async () => {
    const { container } = renderPage()
    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('announces the field error and points the input at it', async () => {
    const user = userEvent.setup()
    const { container } = renderPage()

    await user.click(screen.getByRole('button', { name: 'Login' }))

    // The message is a live region, so it is spoken when it appears. Focus
    // moving to the field is not enough on its own: the focus call runs before
    // React commits the error, so the input is described by nothing yet at the
    // moment the reader lands on it.
    const alerts = await screen.findAllByRole('alert')
    expect(alerts.map((node) => node.textContent)).toContain(
      'Enter your email address.',
    )

    const email = screen.getByLabelText('Email')
    expect(email).toHaveAttribute('aria-invalid', 'true')
    expect(email).toHaveAttribute('aria-describedby', 'email-error')
    expect(document.getElementById('email-error')).toHaveTextContent(
      'Enter your email address.',
    )
    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('has no axe violations with a rejected sign-in shown', async () => {
    const user = userEvent.setup()
    vi.mocked(login).mockRejectedValue(
      new Error('That email and password do not match an account.'),
    )
    const { container } = renderPage()

    await user.type(screen.getByLabelText('Email'), 'ada@example.com')
    await user.type(screen.getByLabelText('Password'), 'hunter2!pass')
    await user.click(screen.getByRole('button', { name: 'Login' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/do not match/i)
    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('keeps the reveal toggle labelled and stateful when the password shows', async () => {
    const user = userEvent.setup()
    const { container } = renderPage()

    const toggle = screen.getByRole('button', { name: /show password/i })
    expect(toggle).toHaveAttribute('aria-pressed', 'false')

    await user.click(toggle)

    // Same control, new state and new name — not a second button appearing.
    const pressed = screen.getByRole('button', { name: /hide password/i })
    expect(pressed).toHaveAttribute('aria-pressed', 'true')
    expect(await axeCheck(container)).toHaveNoViolations()
  })
})
