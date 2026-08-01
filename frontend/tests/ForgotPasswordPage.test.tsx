import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axeCheck } from './a11y'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('@/lib/auth', () => ({
  login: vi.fn(),
  signup: vi.fn(),
  requestPasswordReset: vi.fn(),
}))

import ForgotPasswordPage from '@/app/forgot-password/page'
import { requestPasswordReset } from '@/lib/auth'

const mockedRequest = vi.mocked(requestPasswordReset)

describe('ForgotPasswordPage', () => {
  beforeEach(() => {
    mockedRequest.mockReset()
  })

  it('has no axe violations', async () => {
    const { container } = render(<ForgotPasswordPage />)
    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('rejects a malformed address without calling the API', async () => {
    const user = userEvent.setup()
    render(<ForgotPasswordPage />)

    await user.type(screen.getByLabelText('Email'), 'not-an-email')
    await user.click(screen.getByRole('button', { name: /send reset link/i }))

    expect(screen.getByText('Enter a valid email address.')).toBeInTheDocument()
    expect(mockedRequest).not.toHaveBeenCalled()
  })

  it('sends the address and confirms without revealing whether it is registered', async () => {
    const user = userEvent.setup()
    mockedRequest.mockResolvedValue(undefined)
    render(<ForgotPasswordPage />)

    await user.type(screen.getByLabelText('Email'), '  ada@example.com  ')
    await user.click(screen.getByRole('button', { name: /send reset link/i }))

    expect(mockedRequest).toHaveBeenCalledWith('ada@example.com')
    // "If an account exists" is the whole point: a message that confirmed the
    // address would turn this form into an account-enumeration tool.
    const confirmation = await screen.findByRole('status')
    expect(confirmation).toHaveTextContent(/if an account exists/i)
    expect(confirmation).not.toHaveTextContent(/we sent|your account/i)
  })

  it('surfaces an API failure and keeps the form on screen', async () => {
    const user = userEvent.setup()
    mockedRequest.mockRejectedValue(
      new Error('Something went wrong on our side. Try again in a moment.'),
    )
    render(<ForgotPasswordPage />)

    await user.type(screen.getByLabelText('Email'), 'ada@example.com')
    await user.click(screen.getByRole('button', { name: /send reset link/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/on our side/i)
    expect(screen.getByLabelText('Email')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /send reset link/i })).toBeEnabled()
  })

  it('blocks a second submit while the first is in flight', async () => {
    const user = userEvent.setup()
    mockedRequest.mockReturnValue(new Promise(() => {}))
    render(<ForgotPasswordPage />)

    await user.type(screen.getByLabelText('Email'), 'ada@example.com')
    const submit = screen.getByRole('button', { name: /send reset link/i })
    await user.click(submit)

    expect(submit).toBeDisabled()
    await user.click(submit)
    expect(mockedRequest).toHaveBeenCalledTimes(1)
  })
})
