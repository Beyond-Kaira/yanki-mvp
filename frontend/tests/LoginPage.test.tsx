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

import LoginPage from '@/app/login/page'
import { login } from '@/lib/auth'

const mockedLogin = vi.mocked(login)

describe('LoginPage', () => {
  beforeEach(() => {
    push.mockReset()
    mockedLogin.mockReset()
  })

  it('has no axe violations', async () => {
    const { container } = render(<LoginPage />)
    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('reports each field under its own input and posts nothing', async () => {
    const user = userEvent.setup()
    render(<LoginPage />)

    await user.click(screen.getByRole('button', { name: 'Log in' }))

    expect(screen.getByText('Enter your email address.')).toBeInTheDocument()
    expect(screen.getByText('Enter your password.')).toBeInTheDocument()
    expect(mockedLogin).not.toHaveBeenCalled()
    // The message is wired to the field it belongs to.
    expect(screen.getByLabelText('Email')).toHaveAttribute(
      'aria-describedby',
      'email-error',
    )
  })

  it('rejects a malformed address without calling the API', async () => {
    const user = userEvent.setup()
    render(<LoginPage />)

    await user.type(screen.getByLabelText('Email'), 'not-an-email')
    await user.type(screen.getByLabelText('Password'), 'hunter2!')
    await user.click(screen.getByRole('button', { name: 'Log in' }))

    expect(screen.getByText('Enter a valid email address.')).toBeInTheDocument()
    expect(mockedLogin).not.toHaveBeenCalled()
  })

  it('sends the credentials and the remember choice, then redirects', async () => {
    const user = userEvent.setup()
    mockedLogin.mockResolvedValue(undefined)
    render(<LoginPage />)

    await user.type(screen.getByLabelText('Email'), '  ada@example.com  ')
    await user.type(screen.getByLabelText('Password'), 'hunter2!')
    await user.click(screen.getByLabelText('Remember me'))
    await user.click(screen.getByRole('button', { name: 'Log in' }))

    expect(mockedLogin).toHaveBeenCalledWith({
      email: 'ada@example.com',
      password: 'hunter2!',
      remember: true,
    })
    expect(push).toHaveBeenCalledWith('/')
  })

  it('surfaces an API failure and leaves the form usable', async () => {
    const user = userEvent.setup()
    mockedLogin.mockRejectedValue(
      new Error('That email and password do not match an account.'),
    )
    render(<LoginPage />)

    await user.type(screen.getByLabelText('Email'), 'ada@example.com')
    await user.type(screen.getByLabelText('Password'), 'wrong-one')
    await user.click(screen.getByRole('button', { name: 'Log in' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/do not match an account/i)
    expect(push).not.toHaveBeenCalled()
    // Submitting is over, so a retry is possible.
    expect(screen.getByRole('button', { name: 'Log in' })).toBeEnabled()
  })

  it('blocks a second submit while the first is in flight', async () => {
    const user = userEvent.setup()
    // Never settles: the button has to stay disabled on its own.
    mockedLogin.mockReturnValue(new Promise(() => {}))
    render(<LoginPage />)

    await user.type(screen.getByLabelText('Email'), 'ada@example.com')
    await user.type(screen.getByLabelText('Password'), 'hunter2!')

    const submit = screen.getByRole('button', { name: 'Log in' })
    await user.click(submit)

    expect(submit).toBeDisabled()
    await user.click(submit)
    expect(mockedLogin).toHaveBeenCalledTimes(1)
  })

  it('reveals and re-hides the password', async () => {
    const user = userEvent.setup()
    render(<LoginPage />)

    const field = screen.getByLabelText('Password')
    const toggle = screen.getByRole('button', { name: /show password/i })

    expect(field).toHaveAttribute('type', 'password')
    await user.click(toggle)
    expect(field).toHaveAttribute('type', 'text')

    await user.click(screen.getByRole('button', { name: /hide password/i }))
    expect(field).toHaveAttribute('type', 'password')
  })
})
