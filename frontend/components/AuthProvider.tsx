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
import { acceptInvitation } from '@/lib/api'
import { getActiveOrgId, setActiveOrgId } from '@/lib/active-org'
import { onSessionLost, refreshAccessToken, setAccessToken } from '@/lib/session'

// Drop a stored active-org that the authoritative `/auth/me` list no longer
// contains — a membership revoked while it was selected, or a value left behind
// by a different user on this browser. Without this, every request would keep
// sending an `X-Org-Id` the server 403s, wedging the session; clearing it falls
// the caller back to their first org, which `/auth/me` has already returned.
function reconcileActiveOrg(current: AuthUser | null): void {
  const active = getActiveOrgId()
  if (!active) return
  const organizations = current?.organizations ?? []
  if (!organizations.some((org) => org.id === active)) {
    setActiveOrgId(null)
  }
}

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
  // Redeems an invitation token and signs the invitee in — the endpoint returns
  // the same session envelope as login, so no second round trip is needed.
  acceptInvite: (token: string, password: string) => Promise<void>
  // Changes which organization a multi-org user is acting in. Sets the scope the
  // API client sends and refetches the identity so the shell reflects it; the
  // caller navigates afterward so org-scoped screens reload under the new org.
  switchOrg: (orgId: string) => Promise<void>
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
        // A reload keeps the org the user last switched to (that is the point of
        // persisting it), so reconcile rather than reset — only a value they can
        // no longer use is dropped.
        reconcileActiveOrg(current)
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

  useEffect(
    () =>
      onSessionLost(() => {
        setAccessToken(null)
        setUser(null)
        setStatus('anonymous')
      }),
    [],
  )

  const signIn = useCallback(async (email: string, password: string) => {
    const session = await login({ email, password })
    // A fresh sign-in is a fresh identity: land them in their first org rather
    // than whatever org a previous user on this browser had selected.
    setActiveOrgId(null)
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
        setActiveOrgId(null)
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

  // Accepting an invitation IS a sign-in: the endpoint returns the same
  // { user, access_token } envelope as login and sets the same refresh cookie,
  // so the invitee lands inside the product rather than at a login form holding
  // a password they typed thirty seconds ago.
  const acceptInvite = useCallback(async (token: string, password: string) => {
    const session = await acceptInvitation(token, password)
    setAccessToken(session.access_token)
    setActiveOrgId(null)
    setUser((await fetchCurrentUser()) ?? (session.user as AuthUser))
    setStatus('authenticated')
  }, [])

  // A switch is the stored scope plus a re-read of who we are: `/auth/me` now
  // honours `X-Org-Id`, so it returns the switched org as the singular
  // organization/role/permissions the shell renders. Navigation is the caller's
  // job — org-scoped screens reload their data under the new scope on the way.
  const switchOrg = useCallback(async (orgId: string) => {
    setActiveOrgId(orgId)
    const current = await fetchCurrentUser()
    reconcileActiveOrg(current)
    if (current) setUser(current)
  }, [])

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
      // Drop the selected org too, so the next person to sign in on this browser
      // does not inherit a scope that is not theirs.
      setActiveOrgId(null)
      setUser(null)
      setStatus('anonymous')
    }
  }, [])

  return (
    <AuthContext.Provider
      value={{ status, user, signIn, signUp, signOut, acceptInvite, switchOrg }}
    >
      {children}
    </AuthContext.Provider>
  )
}
