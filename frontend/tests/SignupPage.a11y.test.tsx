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
  // The provider buttons ask the API which providers exist; none configured
  // means they render nothing, which is what these password-form tests assume.
  fetchAuthProviders: vi.fn().mockResolvedValue({ google: null, apple: null }),
  signInWithProvider: vi.fn(),
  SignedUpButNotSignedInError: class SignedUpButNotSignedInError extends Error {},
}))

vi.mock('@/lib/session', () => ({
  refreshAccessToken: vi.fn(),
  setAccessToken: vi.fn(),
  getAccessToken: vi.fn(() => null),
  onSessionLost: vi.fn(() => () => {}),
}))

import AuthProvider from '@/components/AuthProvider'
import SignupPage from '@/app/signup/page'
import { refreshAccessToken } from '@/lib/session'

function renderPage() {
  return render(
    <AuthProvider>
      <SignupPage />
    </AuthProvider>,
  )
}

describe('SignupPage accessibility', () => {
  beforeEach(() => {
    vi.mocked(refreshAccessToken).mockReset().mockResolvedValue(null)
  })

  it('has no axe violations on the default render', async () => {
    const { container } = renderPage()
    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('announces every field error and describes each input by its own', async () => {
    const user = userEvent.setup()
    const { container } = renderPage()

    await user.click(screen.getByRole('button', { name: 'Sign up' }))

    const spoken = (await screen.findAllByRole('alert')).map(
      (node) => node.textContent,
    )
    expect(spoken).toEqual(
      expect.arrayContaining([
        'Enter your email address.',
        'Choose a password.',
        'Re-enter your password.',
      ]),
    )

    // Each field points at its own message rather than at a shared summary, so
    // a reader moving between inputs hears the reason for the one it is on.
    for (const [label, id] of [
      ['Work email', 'email'],
      ['Password', 'password'],
      ['Confirm password', 'confirm-password'],
    ] as const) {
      const field = screen.getByLabelText(label)
      expect(field).toHaveAttribute('aria-invalid', 'true')
      expect(field).toHaveAttribute('aria-describedby', `${id}-error`)
    }

    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('replaces the password hint with the error rather than showing both', async () => {
    const user = userEvent.setup()
    const { container } = renderPage()

    const password = screen.getByLabelText('Password')
    expect(password).toHaveAttribute('aria-describedby', 'password-hint')

    await user.type(password, 'short')
    await user.click(screen.getByRole('button', { name: 'Sign up' }))

    // The rule they have already broken is not what they need read back.
    expect(password).toHaveAttribute('aria-describedby', 'password-error')
    expect(document.getElementById('password-hint')).toBeNull()
    expect(await axeCheck(container)).toHaveNoViolations()
  })
})
