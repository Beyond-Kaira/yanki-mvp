'use client'

import { useRouter } from 'next/navigation'
import { useEffect } from 'react'
import { useAuth } from '@/components/AuthProvider'

/**
 * Gate a route on being signed in.
 *
 * Enforced client-side, and that is a considered choice rather than a
 * shortcut: the refresh cookie is httpOnly and path-scoped to
 * `/api/v1/auth`, so it is never sent to an app route and Next's edge
 * middleware has nothing to read. A middleware guard here would have to
 * trust something the browser can forge.
 *
 * What this protects is the SHELL — the signed-in product surface. It is
 * not the last line of defence for data: every API route enforces its own
 * org scoping and permissions independently, so a determined visitor who
 * skips the UI still gets 401s and 404s. This exists so a signed-out person
 * never sees a product page at all, which is a different and equally real
 * requirement.
 *
 * Three states, and the middle one matters most. While the session is still
 * resolving we render a neutral placeholder rather than the redirect —
 * bouncing someone to /login during a cold load would sign them out on
 * every refresh, which is exactly the bug this component is meant to avoid.
 */
export default function RequireAuth({ children }: { children: React.ReactNode }) {
  const { status } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (status !== 'anonymous') return
    // Read the location directly rather than via `useSearchParams`. The hook
    // opts the whole subtree out of static prerendering unless it is wrapped in
    // Suspense, and this only ever runs in the browser — so the hook would buy
    // a build-time constraint for a value we already have.
    const next = `${window.location.pathname}${window.location.search}`
    router.replace(`/login?next=${encodeURIComponent(next || '/dashboard')}`)
  }, [status, router])

  if (status === 'authenticated') return <>{children}</>

  return (
    <div
      className="flex min-h-[60vh] items-center justify-center px-6"
      role="status"
      aria-live="polite"
    >
      <p className="text-sm text-surface-subtle">
        {status === 'loading' ? 'Checking your session…' : 'Redirecting to sign in…'}
      </p>
    </div>
  )
}
