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
import { useAuth } from '@/components/AuthProvider'
import CustomFormError from '@/components/CustomFormError'
import { fetchAuthProviders } from '@/lib/auth'
import type { AuthProviders, OAuthProvider } from '@/lib/auth'

const GOOGLE_SDK = 'https://accounts.google.com/gsi/client'
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
          renderButton: (parent: HTMLElement, options: Record<string, unknown>) => void
        }
      }
    }
    AppleID?: {
      auth: {
        init: (config: {
          clientId: string
          scope: string
          redirectURI: string
          usePopup: boolean
        }) => void
        signIn: () => Promise<{ authorization?: { id_token?: string } }>
      }
    }
  }
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
  const googleTarget = useRef<HTMLDivElement | null>(null)

  // Held in a ref so the Google callback — registered once, inside an effect —
  // never closes over a stale copy of the sign-in handler.
  const submit = useRef<(provider: OAuthProvider, idToken: string) => void>(() => {})

  const handleToken = useCallback(
    async (provider: OAuthProvider, idToken: string) => {
      setError(null)
      setBusy(true)
      try {
        await signInWithIdToken({
          provider,
          id_token: idToken,
          account_type: accountType,
          organization_name: organizationName ?? null,
        })
        onSignedIn()
      } catch (err) {
        setBusy(false)
        setError(
          err instanceof Error ? err.message : "We couldn't sign you in. Try again.",
        )
      }
    },
    [signInWithIdToken, accountType, organizationName, onSignedIn],
  )

  useEffect(() => {
    submit.current = (provider, idToken) => {
      void handleToken(provider, idToken)
    }
  }, [handleToken])

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

    loadScript(GOOGLE_SDK)
      .then(() => {
        if (cancelled || !googleTarget.current || !window.google) return
        window.google.accounts.id.initialize({
          client_id: googleClientId,
          callback: (response) => submit.current('google', response.credential),
        })
        // Google's own button, because their branding terms ask for it and it
        // is the surface their SDK supports.
        window.google.accounts.id.renderButton(googleTarget.current, {
          theme: 'outline',
          size: 'large',
          text: 'continue_with',
          width: 320,
        })
      })
      .catch(() => {
        if (!cancelled) setError('Google sign-in could not load. Try again.')
      })

    return () => {
      cancelled = true
    }
  }, [googleClientId])

  const appleClientId = providers?.apple ?? null

  async function handleApple() {
    if (!appleClientId) return
    setError(null)
    try {
      await loadScript(APPLE_SDK)
      if (!window.AppleID) throw new Error('Apple sign-in could not load.')
      window.AppleID.auth.init({
        clientId: appleClientId,
        scope: 'name email',
        // Must be registered on the Apple Services ID. With `usePopup` the
        // browser never navigates here — the token comes back to this tab —
        // but Apple still checks the value against the registered list.
        redirectURI: window.location.origin,
        usePopup: true,
      })
      const data = await window.AppleID.auth.signIn()
      const idToken = data.authorization?.id_token
      if (!idToken) throw new Error('Apple did not return a sign-in token.')
      await handleToken('apple', idToken)
    } catch (err) {
      // Closing Apple's popup is a decision, not a failure, and reporting it as
      // an error would put a red message under a button the person just
      // declined to use.
      if (isPopupDismissal(err)) return
      setError(
        err instanceof Error ? err.message : "We couldn't sign you in with Apple.",
      )
    }
  }

  // Nothing to offer, or not known yet: the form above stands on its own, so
  // this renders nothing at all rather than an empty divider.
  if (!googleClientId && !appleClientId) return null

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3" aria-hidden="true">
        <span className="h-px flex-1 bg-surface-border" />
        <span className="text-xs uppercase tracking-wide text-surface-subtle">or</span>
        <span className="h-px flex-1 bg-surface-border" />
      </div>

      <div className={disabled || busy ? 'pointer-events-none opacity-60' : undefined}>
        {googleClientId ? (
          <div ref={googleTarget} className="flex justify-center [&>div]:w-full" />
        ) : null}

        {appleClientId ? (
          <button
            type="button"
            onClick={handleApple}
            disabled={disabled || busy}
            className="mt-3 flex h-11 w-full items-center justify-center gap-2 rounded-md bg-black px-5 text-base font-medium text-white hover:bg-neutral-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-60"
          >
            <AppleMark />
            Continue with Apple
          </button>
        ) : null}
      </div>

      {error ? <CustomFormError id="social-sign-in-error">{error}</CustomFormError> : null}
    </div>
  )
}

// Apple's popup reports a dismissal as an error like { error: 'popup_closed_by_user' }.
function isPopupDismissal(err: unknown): boolean {
  if (typeof err !== 'object' || err === null) return false
  const code = (err as { error?: unknown }).error
  return code === 'popup_closed_by_user' || code === 'user_cancelled_authorize'
}

function AppleMark() {
  return (
    <svg aria-hidden="true" viewBox="0 0 384 512" className="h-4 w-4 fill-current">
      <path d="M318.7 268.7c-.2-36.7 16.4-64.4 50-84.8-18.8-26.9-47.2-41.7-84.7-44.6-35.5-2.8-74.3 20.7-88.5 20.7-15 0-49.4-19.7-76.4-19.7C63.3 141.2 4 184.8 4 273.5q0 39.3 14.4 81.2c12.8 36.7 59 126.7 107.2 125.2 25.2-.6 43-17.9 75.8-17.9 31.8 0 48.3 17.9 76.4 17.9 48.6-.7 90.4-82.5 102.6-119.3-65.2-30.7-61.7-90-61.7-91.9zm-56.6-164.2c27.3-32.4 24.8-61.9 24-72.5-24.1 1.4-52 16.4-67.9 34.9-17.5 19.8-27.8 44.3-25.6 71.9 26.1 2 49.9-11.4 69.5-34.3z" />
    </svg>
  )
}
