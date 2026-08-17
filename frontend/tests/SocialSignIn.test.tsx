import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import SocialSignIn from '@/components/SocialSignIn'
import { ApiError } from '@/lib/api'
import { AccountLinkRequiredError } from '@/lib/auth'

const signInWithIdToken = vi.fn()
const fetchAuthProviders = vi.fn()

vi.mock('@/components/AuthProvider', () => ({
  useAuth: () => ({ signInWithIdToken }),
}))

vi.mock('@/lib/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/auth')>()
  return { ...actual, fetchAuthProviders: () => fetchAuthProviders() }
})

// The SDKs install themselves on `window` when their script loads, and jsdom
// fetches nothing and therefore never fires `load`. Appending a script here
// resolves it instead, so the component's loader behaves as it does in a
// browser without a single request leaving the test.
function serveScriptsLocally() {
  const append = document.head.appendChild.bind(document.head)
  vi.spyOn(document.head, 'appendChild').mockImplementation(((node: Node) => {
    const appended = append(node)
    if (node instanceof HTMLScriptElement) {
      queueMicrotask(() => node.dispatchEvent(new Event('load')))
    }
    return appended
  }) as typeof document.head.appendChild)
}

const googleId = {
  initialize: vi.fn(),
  renderButton: vi.fn((parent: HTMLElement) => {
    parent.innerHTML = '<div role="button">Continue with Google</div>'
  }),
}

const appleAuth = {
  init: vi.fn(),
}

function dispatchAppleSuccess(state?: string) {
  document.dispatchEvent(
    new CustomEvent('AppleIDSignInOnSuccess', {
      detail: {
        data: {
          authorization: {
            id_token: 'apple-token',
            state: state ?? appleAuth.init.mock.calls[0][0].state,
          },
        },
      },
    }),
  )
}

function dispatchAppleFailure(error: string) {
  document.dispatchEvent(
    new CustomEvent('AppleIDSignInOnFailure', { detail: { error } }),
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  serveScriptsLocally()
  window.google = { accounts: { id: googleId } }
  window.AppleID = { auth: appleAuth }
  fetchAuthProviders.mockResolvedValue({
    google: 'google-client',
    apple: 'com.yanki.web',
  })
  appleAuth.init.mockImplementation(() => {
    const parent = document.getElementById('appleid-signin')
    if (parent)
      parent.innerHTML = '<button type="button">Continue with Apple</button>'
  })
})

afterEach(() => {
  vi.restoreAllMocks()
  document.querySelectorAll('script').forEach((script) => script.remove())
})

describe('SocialSignIn', () => {
  it('renders nothing when the deployment has no provider configured', async () => {
    fetchAuthProviders.mockResolvedValue({ google: null, apple: null })

    const { container } = render(<SocialSignIn onSignedIn={vi.fn()} />)

    await waitFor(() => expect(fetchAuthProviders).toHaveBeenCalled())
    // Not an empty divider, not a dead button: nothing.
    expect(container).toBeEmptyDOMElement()
  })

  it('offers only the provider that is configured', async () => {
    fetchAuthProviders.mockResolvedValue({
      google: null,
      apple: 'com.yanki.web',
    })

    render(<SocialSignIn onSignedIn={vi.fn()} />)

    expect(
      await screen.findByRole('button', { name: /continue with apple/i }),
    ).toBeInTheDocument()
    await waitFor(() => expect(googleId.renderButton).not.toHaveBeenCalled())
  })

  it("sends Apple's identity token and nothing the client could have made up", async () => {
    const onSignedIn = vi.fn()
    render(
      <SocialSignIn
        accountType="organization"
        organizationName="Kaira"
        onSignedIn={onSignedIn}
      />,
    )

    await userEvent.click(
      await screen.findByRole('button', { name: /continue with apple/i }),
    )
    dispatchAppleSuccess()

    await waitFor(() =>
      expect(signInWithIdToken).toHaveBeenCalledWith({
        provider: 'apple',
        id_token: 'apple-token',
        account_type: 'organization',
        organization_name: 'Kaira',
      }),
    )
    await waitFor(() => expect(onSignedIn).toHaveBeenCalled())
  })

  it("hands Google's credential to the same sign-in call", async () => {
    const onSignedIn = vi.fn()
    render(<SocialSignIn onSignedIn={onSignedIn} />)

    await waitFor(() => expect(googleId.initialize).toHaveBeenCalled())

    // Fire the callback the SDK was given, exactly as Google's button would.
    googleId.initialize.mock.calls[0][0].callback({
      credential: 'google-token',
    })

    await waitFor(() =>
      expect(signInWithIdToken).toHaveBeenCalledWith({
        provider: 'google',
        id_token: 'google-token',
        account_type: undefined,
        organization_name: null,
      }),
    )
    await waitFor(() => expect(onSignedIn).toHaveBeenCalled())
  })

  it('confirms an existing password before connecting Google', async () => {
    const onSignedIn = vi.fn()
    signInWithIdToken
      .mockRejectedValueOnce(new AccountLinkRequiredError())
      .mockResolvedValueOnce(undefined)
    render(<SocialSignIn onSignedIn={onSignedIn} />)

    await waitFor(() => expect(googleId.initialize).toHaveBeenCalled())
    googleId.initialize.mock.calls[0][0].callback({
      credential: 'google-token',
    })

    expect(
      await screen.findByRole('heading', { name: /connect google/i }),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/your password login will stay active/i),
    ).toBeInTheDocument()

    await userEvent.type(
      screen.getByLabelText(/current password/i),
      'hunter2hunter2',
    )
    await userEvent.click(
      screen.getByRole('button', { name: /connect and continue/i }),
    )

    await waitFor(() =>
      expect(signInWithIdToken).toHaveBeenLastCalledWith({
        provider: 'google',
        id_token: 'google-token',
        account_type: undefined,
        organization_name: null,
        password: 'hunter2hunter2',
      }),
    )
    await waitFor(() => expect(onSignedIn).toHaveBeenCalled())
  })

  it('reports a rejected sign-in in words, and does not navigate', async () => {
    const onSignedIn = vi.fn()
    signInWithIdToken.mockRejectedValue(
      new ApiError('That sign-in could not be verified. Try again.', 401),
    )
    render(<SocialSignIn onSignedIn={onSignedIn} />)

    await userEvent.click(
      await screen.findByRole('button', { name: /continue with apple/i }),
    )
    dispatchAppleSuccess()

    expect(
      await screen.findByText(/could not be verified/i),
    ).toBeInTheDocument()
    expect(onSignedIn).not.toHaveBeenCalled()
  })

  it('stays quiet when the person closes the Apple popup', async () => {
    render(<SocialSignIn onSignedIn={vi.fn()} />)

    await userEvent.click(
      await screen.findByRole('button', { name: /continue with apple/i }),
    )
    dispatchAppleFailure('user_cancelled_authorize')

    // Declining is not a failure, so there is nothing to apologise for.
    await waitFor(() => expect(signInWithIdToken).not.toHaveBeenCalled())
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('rejects an Apple response whose state is not the one this page issued', async () => {
    render(<SocialSignIn onSignedIn={vi.fn()} />)

    await userEvent.click(
      await screen.findByRole('button', { name: /continue with apple/i }),
    )
    dispatchAppleSuccess('state-from-another-page')

    expect(
      await screen.findByText(/could not be verified/i),
    ).toBeInTheDocument()
    expect(signInWithIdToken).not.toHaveBeenCalled()
  })

  it('uses the provider-rendered Apple button and responsive Google width', async () => {
    render(<SocialSignIn onSignedIn={vi.fn()} />)

    await screen.findByRole('button', { name: /continue with apple/i })
    const appleTarget = document.getElementById('appleid-signin')
    expect(appleTarget).toHaveAttribute('data-type', 'continue')
    expect(appleTarget).toHaveAttribute('data-width', '100%')
    expect(appleAuth.init).toHaveBeenCalledWith(
      expect.objectContaining({ state: expect.any(String), usePopup: true }),
    )
    expect(googleId.renderButton).toHaveBeenCalledWith(
      expect.any(HTMLElement),
      expect.objectContaining({ width: 320, shape: 'rectangular' }),
    )
  })

  it('does not open social sign-in before an organization has a name', async () => {
    render(
      <SocialSignIn
        accountType="organization"
        organizationName=""
        onSignedIn={vi.fn()}
      />,
    )

    expect(
      await screen.findByText(/enter an organization name to continue/i),
    ).toBeInTheDocument()
    const appleButton = await screen.findByRole('button', {
      name: /continue with apple/i,
    })
    await userEvent.click(appleButton)
    dispatchAppleSuccess()

    await waitFor(() => expect(signInWithIdToken).not.toHaveBeenCalled())
  })
})
