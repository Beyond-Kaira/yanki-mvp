'use client'

import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import {
  SignedUpButNotSignedInError,
  fetchCurrentUser,
  login,
  logout as logoutRequest,
  signup,
} from '@/lib/auth'
import type { AuthUser } from '@/lib/auth'
import { refreshAccessToken, setAccessToken } from '@/lib/session'

// 'loading' is its own state rather than "anonymous until proven otherwise": on
// a cold load the app genuinely does not know yet, and rendering signed-out
// chrome first makes a returning visitor's header flicker.
type AuthStatus = 'loading' | 'authenticated' | 'anonymous'

interface AuthContextValue {
  status: AuthStatus
  user: AuthUser | null
  signIn: (email: string, password: string) => Promise<void>
  // Creates the account and signs in with the same credentials, because the
  // signup endpoint returns no session of its own.
  signUp: (
    email: string,
    password: string,
    options?: { accountType?: 'individual' | 'organization'; organizationName?: string },
  ) => Promise<void>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}

export default function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [user, setUser] = useState<AuthUser | null>(null)

  // The access token lives in memory, so a reload starts with none. The refresh
  // cookie survives, so the way back in is to rotate it and then ask who we are.
  useEffect(() => {
    let cancelled = false

    async function restore() {
      const token = await refreshAccessToken()
      if (cancelled) return
      if (!token) {
        setStatus('anonymous')
        return
      }

      try {
        const current = await fetchCurrentUser()
        if (cancelled) return
        setUser(current)
        setStatus(current ? 'authenticated' : 'anonymous')
      } catch {
        // A token that cannot be spent is not a session worth reporting.
        if (cancelled) return
        setAccessToken(null)
        setStatus('anonymous')
      }
    }

    restore()
    return () => {
      cancelled = true
    }
  }, [])

  const signIn = useCallback(async (email: string, password: string) => {
    const session = await login({ email, password })
    // `login` returns the narrow user; `/auth/me` returns the same person plus
    // their organization, role and permissions. Fetching it here means the
    // shell shows "Acme · Owner" from the first painted frame instead of a bare
    // email that only becomes an identity after the next page load.
    setUser((await fetchCurrentUser()) ?? session.user)
    setStatus('authenticated')
  }, [])

  const signUp = useCallback(
    async (
      email: string,
      password: string,
      options?: { accountType?: 'individual' | 'organization'; organizationName?: string },
    ) => {
      await signup({
        email,
        password,
        account_type: options?.accountType ?? 'individual',
        organization_name: options?.organizationName ?? null,
      })

      // Signing up leaves you anonymous, so spend the credentials we already
      // hold rather than sending someone to type them a second time. Past this
      // line the account exists, so a failure here is a different story to tell.
      try {
        const session = await login({ email, password })
        setUser((await fetchCurrentUser()) ?? session.user)
        setStatus('authenticated')
      } catch (err) {
        throw new SignedUpButNotSignedInError(
          err instanceof Error ? err.message : 'Sign-in failed.',
        )
      }
    },
    [],
  )

  // Signing out always succeeds locally. Whatever the request does, the token is
  // dropped and the state clears, and the caller is given nothing to handle:
  // there is no useful recovery from "we could not tell the server", and an
  // error escaping here reaches a click handler that has no answer for it.
  const signOut = useCallback(async () => {
    try {
      await logoutRequest()
    } catch {
      // Already signed out on this device; the server-side cookie expires.
    } finally {
      setUser(null)
      setStatus('anonymous')
    }
  }, [])

  return (
    <AuthContext.Provider value={{ status, user, signIn, signUp, signOut }}>
      {children}
    </AuthContext.Provider>
  )
}
