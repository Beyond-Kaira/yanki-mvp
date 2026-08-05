import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import InviteClient from '@/app/invite/[token]/InviteClient'
import { ApiError } from '@/lib/api'

const previewInvitation = vi.fn()
const acceptInvite = vi.fn()
const push = vi.fn()

let authState: { status: string; user: { email: string } | null } = {
  status: 'anonymous',
  user: null,
}

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    previewInvitation: (...args: unknown[]) => previewInvitation(...args),
  }
})

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
}))

vi.mock('@/components/AuthProvider', () => ({
  useAuth: () => ({ ...authState, acceptInvite }),
}))

const PREVIEW = {
  email: 'newbie@acme.test',
  role: 'analyst',
  organization_name: 'Acme Industries',
  expires_at: '2026-08-19T00:00:00Z',
}

describe('InviteClient', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authState = { status: 'anonymous', user: null }
    previewInvitation.mockResolvedValue(PREVIEW)
    acceptInvite.mockResolvedValue(undefined)
  })

  it('says what is being joined and in what role', async () => {
    render(<InviteClient token="tok-abc" />)

    expect(await screen.findByRole('heading', { name: /join acme industries/i })).toBeVisible()
    expect(screen.getByText('Analyst')).toBeVisible()
    expect(screen.getByText('newbie@acme.test')).toBeVisible()
  })

  it('does not offer the email as an editable field', async () => {
    render(<InviteClient token="tok-abc" />)
    await screen.findByText('newbie@acme.test')

    // An editable address would turn an invitation addressed to one person into
    // a way to create an account as another, holding the first one's role.
    expect(screen.queryByLabelText(/email/i)).not.toBeInTheDocument()
  })

  it('creates the account and lands the invitee inside the product', async () => {
    const user = userEvent.setup()
    render(<InviteClient token="tok-abc" />)
    await screen.findByText('newbie@acme.test')

    await user.type(screen.getByLabelText('Choose a password'), 'a-good-long-password')
    await user.type(screen.getByLabelText('Confirm password'), 'a-good-long-password')
    await user.click(screen.getByRole('button', { name: /create account and join/i }))

    await waitFor(() => expect(acceptInvite).toHaveBeenCalledWith('tok-abc', 'a-good-long-password'))
    await waitFor(() => expect(push).toHaveBeenCalledWith('/dashboard'))
  })

  it('refuses a mismatched confirmation before calling the API', async () => {
    const user = userEvent.setup()
    render(<InviteClient token="tok-abc" />)
    await screen.findByText('newbie@acme.test')

    await user.type(screen.getByLabelText('Choose a password'), 'a-good-long-password')
    await user.type(screen.getByLabelText('Confirm password'), 'something-else-entirely')
    await user.click(screen.getByRole('button', { name: /create account and join/i }))

    expect(acceptInvite).not.toHaveBeenCalled()
  })

  it('explains an expired link in the server\'s own words', async () => {
    previewInvitation.mockRejectedValue(
      new ApiError(
        'This invitation has expired. Ask whoever invited you to send a new one.',
        410,
      ),
    )
    render(<InviteClient token="tok-old" />)

    expect(await screen.findByRole('heading', { name: /can't be used/i })).toBeVisible()
    expect(screen.getByRole('alert')).toHaveTextContent(/expired/i)
    // A dead end still offers the way forward for someone who does have an account.
    expect(screen.getByRole('link', { name: /sign in/i })).toBeVisible()
  })

  it('explains a withdrawn link', async () => {
    previewInvitation.mockRejectedValue(
      new ApiError('This invitation was withdrawn. Ask whoever invited you to send a new one.', 410),
    )
    render(<InviteClient token="tok-gone" />)

    expect(await screen.findByRole('alert')).toHaveTextContent(/withdrawn/i)
  })

  it('explains an unknown link without pretending it was ever valid', async () => {
    previewInvitation.mockRejectedValue(new ApiError('That invitation link is not valid.', 404))
    render(<InviteClient token="nonsense" />)

    expect(await screen.findByRole('alert')).toHaveTextContent('That invitation link is not valid.')
  })

  it('asks a signed-in invitee to join rather than for a password', async () => {
    const user = userEvent.setup()
    authState = { status: 'authenticated', user: { email: 'newbie@acme.test' } }
    render(<InviteClient token="tok-abc" />)
    await screen.findByText(/already signed in as newbie@acme.test/i)

    expect(screen.queryByLabelText('Choose a password')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /join organization/i }))

    await waitFor(() => expect(acceptInvite).toHaveBeenCalled())
  })

  it('stops someone signed in as a different person from taking the seat', async () => {
    authState = { status: 'authenticated', user: { email: 'someone@else.test' } }
    render(<InviteClient token="tok-abc" />)
    await screen.findByText('newbie@acme.test')

    expect(screen.getByRole('alert')).toHaveTextContent(/signed in as someone@else.test/i)
    expect(screen.getByRole('button', { name: /create account and join/i })).toBeDisabled()
  })

  it("surfaces the server's refusal on accept", async () => {
    const user = userEvent.setup()
    acceptInvite.mockRejectedValue(
      new ApiError('An account already exists for this address. Sign in first.', 409),
    )
    render(<InviteClient token="tok-abc" />)
    await screen.findByText('newbie@acme.test')

    await user.type(screen.getByLabelText('Choose a password'), 'a-good-long-password')
    await user.type(screen.getByLabelText('Confirm password'), 'a-good-long-password')
    await user.click(screen.getByRole('button', { name: /create account and join/i }))

    expect(
      await screen.findByText('An account already exists for this address. Sign in first.'),
    ).toBeVisible()
  })
})

describe('InviteClient failure messages', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authState = { status: 'anonymous', user: null }
  })

  it('never shows the framework\'s own validator message to an invitee', async () => {
    // A path parameter shorter than the minimum is rejected before any route
    // runs, and Pydantic's sentence — "String should have at least 16
    // characters" — is about our validator, shown to somebody who only knows
    // they clicked a link.
    previewInvitation.mockRejectedValue(
      new ApiError('String should have at least 16 characters', 422),
    )
    render(<InviteClient token="short" />)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('That invitation link is not valid.')
    expect(alert).not.toHaveTextContent(/16 characters/)
  })

  it('says the server is unreachable rather than blaming the link', async () => {
    previewInvitation.mockRejectedValue(new ApiError('boom', 0))
    render(<InviteClient token="a-perfectly-fine-token" />)

    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn't reach the server/i)
  })
})
