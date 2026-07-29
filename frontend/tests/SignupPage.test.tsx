import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axeCheck } from './a11y'

const push = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
}))

vi.mock('@/lib/auth', () => ({
  login: vi.fn(),
  signup: vi.fn(),
}))

import SignupPage from '@/app/signup/page'
import { signup } from '@/lib/auth'

const mockedSignup = vi.mocked(signup)

async function fillValidForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('Full name'), 'Ada Lovelace')
  await user.type(screen.getByLabelText('Work email'), 'ada@example.com')
  await user.type(screen.getByLabelText('Password'), 'hunter2!pass')
  await user.type(screen.getByLabelText('Confirm password'), 'hunter2!pass')
  await user.click(screen.getByLabelText(/I agree to the/))
}

describe('SignupPage', () => {
  beforeEach(() => {
    push.mockReset()
    mockedSignup.mockReset()
  })

  it('has no axe violations', async () => {
    const { container } = render(<SignupPage />)
    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('reports every empty field at once and posts nothing', async () => {
    const user = userEvent.setup()
    render(<SignupPage />)

    await user.click(screen.getByRole('button', { name: 'Sign up' }))

    expect(screen.getByText('Enter your name.')).toBeInTheDocument()
    expect(screen.getByText('Enter your email address.')).toBeInTheDocument()
    expect(screen.getByText('Choose a password.')).toBeInTheDocument()
    expect(screen.getByText('Re-enter your password.')).toBeInTheDocument()
    expect(screen.getByText('Accept the terms to continue.')).toBeInTheDocument()
    expect(mockedSignup).not.toHaveBeenCalled()
  })

  it('rejects a password under the minimum length', async () => {
    const user = userEvent.setup()
    render(<SignupPage />)

    await user.type(screen.getByLabelText('Password'), 'short')
    await user.click(screen.getByRole('button', { name: 'Sign up' }))

    expect(screen.getByText('Use at least 8 characters.')).toBeInTheDocument()
    expect(mockedSignup).not.toHaveBeenCalled()
  })

  it('rejects a confirmation that does not match', async () => {
    const user = userEvent.setup()
    render(<SignupPage />)

    await user.type(screen.getByLabelText('Password'), 'hunter2!pass')
    await user.type(screen.getByLabelText('Confirm password'), 'hunter2!different')
    await user.click(screen.getByRole('button', { name: 'Sign up' }))

    expect(screen.getByText('Passwords do not match.')).toBeInTheDocument()
    expect(mockedSignup).not.toHaveBeenCalled()
  })

  it('blocks submit until the terms are accepted', async () => {
    const user = userEvent.setup()
    render(<SignupPage />)

    await user.type(screen.getByLabelText('Full name'), 'Ada Lovelace')
    await user.type(screen.getByLabelText('Work email'), 'ada@example.com')
    await user.type(screen.getByLabelText('Password'), 'hunter2!pass')
    await user.type(screen.getByLabelText('Confirm password'), 'hunter2!pass')
    await user.click(screen.getByRole('button', { name: 'Sign up' }))

    expect(screen.getByText('Accept the terms to continue.')).toBeInTheDocument()
    expect(mockedSignup).not.toHaveBeenCalled()
  })

  it('sends the account details, and never the confirmation field', async () => {
    const user = userEvent.setup()
    mockedSignup.mockResolvedValue(undefined)
    render(<SignupPage />)

    await fillValidForm(user)
    await user.click(screen.getByRole('button', { name: 'Sign up' }))

    expect(mockedSignup).toHaveBeenCalledWith({
      name: 'Ada Lovelace',
      email: 'ada@example.com',
      password: 'hunter2!pass',
    })
    expect(push).toHaveBeenCalledWith('/')
  })

  it('surfaces an API failure and leaves the form usable', async () => {
    const user = userEvent.setup()
    mockedSignup.mockRejectedValue(
      new Error('An account with that email already exists.'),
    )
    render(<SignupPage />)

    await fillValidForm(user)
    await user.click(screen.getByRole('button', { name: 'Sign up' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/already exists/i)
    expect(push).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Sign up' })).toBeEnabled()
  })

  it('blocks a second submit while the first is in flight', async () => {
    const user = userEvent.setup()
    mockedSignup.mockReturnValue(new Promise(() => {}))
    render(<SignupPage />)

    await fillValidForm(user)
    const submit = screen.getByRole('button', { name: 'Sign up' })
    await user.click(submit)

    expect(submit).toBeDisabled()
    await user.click(submit)
    expect(mockedSignup).toHaveBeenCalledTimes(1)
  })

  it('shows the length rule as a hint, not as an error', async () => {
    render(<SignupPage />)

    const field = screen.getByLabelText('Password')
    expect(field).toHaveAttribute('aria-describedby', 'password-hint')
    expect(field).not.toHaveAttribute('aria-invalid')
  })
})
