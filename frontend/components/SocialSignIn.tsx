'use client'

// Google and Apple sign-in buttons, for the login and sign-up screens.
//
// The provider SDK runs the sign-in in the browser and hands back a signed
// `id_token`; the only thing sent to our API is that token, which the backend
// verifies against the provider's own keys (backend/app/services/oauth.py).
// Nothing this component reports about the user — not the email, not the name —
// is trusted or even transmitted, because a client is free to lie about all of
// it and the token already says it truthfully.
//
// Which buttons appear comes from `/auth/providers` rather than from a build
// time variable, so a provider configured after the image was built still shows
// up, and one that is not configured shows nothing instead of a button that
// answers 503 on click.

import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import Button from '@/components/Button'
import { useAuth } from '@/components/AuthProvider'
import CustomFormError from '@/components/CustomFormError'
import CustomPasswordField from '@/components/CustomPasswordField'
import { AccountLinkRequiredError, fetchAuthProviders } from '@/lib/auth'
import type { AuthProviders, OAuthProvider } from '@/lib/auth'

const GOOGLE_SDK = 'https://accounts.google.com/gsi/client?hl=en'
const APPLE_SDK =
  'https://appleid.cdn-apple.com/appleauth/static/jsapi/appleid/1/en_US/appleid.auth.js'

// Only the handful of SDK surface this file touches. Typing the whole of either
// SDK would be a maintenance burden for no extra safety at the two call sites.
declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: {
            client_id: string
            callback: (response: { credential: string }) => void
          }) => void
          renderButton: (
            parent: HTMLElement,
            options: Record<string, unknown>,
          ) => void
        }
      }
    }
    AppleID?: {
      auth: {
        init: (config: {
          clientId: string
          scope: string
          redirectURI: string
          state: string
          usePopup: boolean
        }) => void
      }
    }
  }
}

interface AppleAuthorization {
  id_token?: string
  state?: string
}

interface AppleSignInDetail {
  data?: { authorization?: AppleAuthorization }
  authorization?: AppleAuthorization
  error?: string
}

interface PendingAccountLink {
  provider: OAuthProvider
  idToken: string
}

// One <script> per URL however many times this renders, and the same promise
// handed to every caller — two mounts of this component must not race two
// copies of an SDK that installs itself on `window`.
const loading = new Map<string, Promise<void>>()

function loadScript(src: string): Promise<void> {
  const started = loading.get(src)
  if (started) return started

  const pending = new Promise<void>((resolve, reject) => {
    const script = document.createElement('script')
    script.src = src
    script.async = true
    script.onload = () => resolve()
    script.onerror = () => {
      // Let a later mount retry: a blocked or flaky CDN should not disable the
      // button for the rest of the visit.
      loading.delete(src)
      reject(new Error(`Could not load ${src}`))
    }
    document.head.appendChild(script)
  })

  loading.set(src, pending)
  return pending
}

export interface SocialSignInProps {
  // Only consulted when the token turns out to belong to nobody yet, which is
  // why the sign-in screen can leave them out entirely.
  accountType?: 'individual' | 'organization'
  organizationName?: string | null
  onSignedIn: () => void
  disabled?: boolean
}

export default function SocialSignIn({
  accountType,
  organizationName,
  onSignedIn,
  disabled = false,
}: SocialSignInProps) {
  const { signInWithIdToken } = useAuth()
  const [providers, setProviders] = useState<AuthProviders | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [pendingLink, setPendingLink] = useState<PendingAccountLink | null>(null)
  const [linkPassword, setLinkPassword] = useState('')
  const googleTarget = useRef<HTMLDivElement | null>(null)
  const appleState = useRef<string | null>(null)
  const tokenSubmissionStarted = useRef(false)

  // Held in a ref so the Google callback — registered once, inside an effect —
  // never closes over a stale copy of the sign-in handler.
  const submit = useRef<(provider: OAuthProvider, idToken: string) => void>(
    () => {},
  )

  const handleToken = useCallback(
    async (provider: OAuthProvider, idToken: string, password?: string) => {
      const organizationMissing =
        accountType === 'organization' && !organizationName?.trim()
      if (disabled || organizationMissing || tokenSubmissionStarted.current)
        return

      tokenSubmissionStarted.current = true
      setError(null)
      setBusy(true)
      try {
        await signInWithIdToken({
          provider,
          id_token: idToken,
          account_type: accountType,
          organization_name: organizationName ?? null,
          ...(password ? { password } : {}),
        })
        setPendingLink(null)
        setLinkPassword('')
        onSignedIn()
      } catch (err) {
        tokenSubmissionStarted.current = false
        setBusy(false)
        if (err instanceof AccountLinkRequiredError) {
          setPendingLink({ provider, idToken })
          setLinkPassword('')
          return
        }
        setError(
          err instanceof Error
            ? err.message
            : "We couldn't sign you in. Try again.",
        )
      }
    },
    [signInWithIdToken, accountType, organizationName, onSignedIn, disabled],
  )

  useEffect(() => {
    submit.current = (provider, idToken) => {
      void handleToken(provider, idToken)
    }
  }, [handleToken])

  function handleLinkSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!pendingLink || !linkPassword || busy) return
    void handleToken(pendingLink.provider, pendingLink.idToken, linkPassword)
  }

  useEffect(() => {
    let cancelled = false
    fetchAuthProviders().then((available) => {
      if (!cancelled) setProviders(available)
    })
    return () => {
      cancelled = true
    }
  }, [])

  const googleClientId = providers?.google ?? null

  useEffect(() => {
    if (!googleClientId) return
    let cancelled = false
    let observer: ResizeObserver | null = null
    let renderedWidth = 0

    loadScript(GOOGLE_SDK)
      .then(() => {
        if (cancelled || !googleTarget.current || !window.google) return
        window.google.accounts.id.initialize({
          client_id: googleClientId,
          callback: (response) => submit.current('google', response.credential),
        })

        const render = () => {
          const target = googleTarget.current
          if (!target || !window.google) return
          // Google accepts 400px at most. Use the real form width so its button
          // lines up with Apple's and the password form instead of being stuck
          // at an arbitrary 320px on every viewport.
          const width = Math.min(
            400,
            Math.max(240, Math.floor(target.clientWidth || 320)),
          )
          if (width === renderedWidth) return
          renderedWidth = width
          target.replaceChildren()
          window.google.accounts.id.renderButton(target, {
            theme: 'outline',
            size: 'large',
            text: 'continue_with',
            shape: 'rectangular',
            locale: 'en',
            width,
          })
        }

        render()
        if (typeof ResizeObserver !== 'undefined') {
          observer = new ResizeObserver(render)
          observer.observe(googleTarget.current)
        }
      })
      .catch(() => {
        if (!cancelled) setError('Google sign-in could not load. Try again.')
      })

    return () => {
      cancelled = true
      observer?.disconnect()
    }
  }, [googleClientId])

  const appleClientId = providers?.apple ?? null

  useEffect(() => {
    if (!appleClientId) return
    let cancelled = false

    const onSuccess = (event: Event) => {
      if (cancelled) return
      const detail = (event as CustomEvent<AppleSignInDetail>).detail
      const authorization = detail?.data?.authorization ?? detail?.authorization
      if (!authorization?.id_token) {
        setBusy(false)
        setError('Apple did not return a sign-in token.')
        return
      }
      if (!appleState.current || authorization.state !== appleState.current) {
        setBusy(false)
        setError('Apple sign-in could not be verified. Try again.')
        return
      }
      submit.current('apple', authorization.id_token)
    }

    const onFailure = (event: Event) => {
      if (cancelled) return
      setBusy(false)
      const detail = (event as CustomEvent<AppleSignInDetail>).detail
      const error = detail?.error
      if (isPopupDismissal({ error })) return
      setError("We couldn't sign you in with Apple. Try again.")
    }

    document.addEventListener('AppleIDSignInOnSuccess', onSuccess)
    document.addEventListener('AppleIDSignInOnFailure', onFailure)

    loadScript(APPLE_SDK)
      .then(() => {
        if (cancelled || !window.AppleID) return
        appleState.current = randomState()
        window.AppleID.auth.init({
          clientId: appleClientId,
          scope: 'name email',
          // This exact origin must be registered on the Apple Services ID.
          // Popup mode keeps the person in this tab, but Apple still validates
          // the redirect URI before returning the result event.
          redirectURI: window.location.origin,
          state: appleState.current,
          usePopup: true,
        })
      })
      .catch(() => {
        if (!cancelled) setError('Apple sign-in could not load. Try again.')
      })

    return () => {
      cancelled = true
      document.removeEventListener('AppleIDSignInOnSuccess', onSuccess)
      document.removeEventListener('AppleIDSignInOnFailure', onFailure)
    }
  }, [appleClientId])

  // Nothing to offer, or not known yet: the form above stands on its own, so
  // this renders nothing at all rather than an empty divider.
  if (!googleClientId && !appleClientId) return null

  const organizationMissing =
    accountType === 'organization' && !organizationName?.trim()
  const socialDisabled = disabled || busy || organizationMissing || pendingLink !== null

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3" aria-hidden="true">
        <span className="h-px flex-1 bg-surface-border" />
        <span className="text-xs uppercase tracking-wide text-surface-subtle">
          or
        </span>
        <span className="h-px flex-1 bg-surface-border" />
      </div>

      <div
        className={
          socialDisabled ? 'pointer-events-none opacity-60' : undefined
        }
        aria-disabled={socialDisabled || undefined}
        inert={socialDisabled}
      >
        {googleClientId ? (
          <div
            ref={googleTarget}
            className="flex min-h-11 w-full justify-center"
          />
        ) : null}

        {appleClientId ? (
          // Let Apple's SDK draw its own trademarked button. The data
          // attributes are Apple's documented web-button API; using it keeps
          // the logo, typography and spacing correct as their UI evolves.
          <div
            id="appleid-signin"
            className="mt-3 h-11 w-full overflow-hidden rounded-md"
            data-color="black"
            data-border="true"
            data-type="continue"
            data-mode="center-align"
            data-border-radius="6"
            data-width="100%"
            data-height="44"
            onClick={() => {
              setError(null)
              setBusy(true)
            }}
          />
        ) : null}
      </div>

      {pendingLink ? (
        <form
          onSubmit={handleLinkSubmit}
          className="space-y-4 rounded-lg border border-surface-border bg-surface-muted p-4"
        >
          <div className="space-y-1">
            <h2 className="text-sm font-semibold text-surface-foreground">
              Connect {pendingLink.provider === 'google' ? 'Google' : 'Apple'}
            </h2>
            <p className="text-sm text-surface-subtle">
              An account with this email already exists. Enter its current
              password to connect {pendingLink.provider === 'google' ? 'Google' : 'Apple'}.
              Your password login will stay active.
            </p>
          </div>

          <CustomPasswordField
            id="account-link-password"
            name="password"
            label="Current password"
            autoComplete="current-password"
            maxLength={128}
            value={linkPassword}
            onChange={(event) => {
              setLinkPassword(event.target.value)
              setError(null)
            }}
            disabled={busy || disabled}
            autoFocus
          />

          <div className="flex gap-3">
            <Button
              type="submit"
              size="sm"
              loading={busy}
              disabled={!linkPassword || disabled}
            >
              Connect and continue
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={busy || disabled}
              onClick={() => {
                setPendingLink(null)
                setLinkPassword('')
                setError(null)
              }}
            >
              Cancel
            </Button>
          </div>
        </form>
      ) : null}

      {organizationMissing ? (
        <p className="text-sm text-surface-subtle">
          Enter an organization name to continue with Google or Apple.
        </p>
      ) : null}

      {error ? (
        <CustomFormError id="social-sign-in-error">{error}</CustomFormError>
      ) : null}
    </div>
  )
}

// Apple's popup reports a dismissal as an error like { error: 'popup_closed_by_user' }.
function isPopupDismissal(err: unknown): boolean {
  if (typeof err !== 'object' || err === null) return false
  const code = (err as { error?: unknown }).error
  return code === 'popup_closed_by_user' || code === 'user_cancelled_authorize'
}

function randomState(): string {
  const bytes = new Uint8Array(24)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join(
    '',
  )
}
