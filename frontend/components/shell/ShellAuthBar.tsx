'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { useAuth } from '@/components/AuthProvider'

const QUIET =
  'inline-flex min-h-[36px] items-center rounded px-2 text-sm font-medium text-surface-subtle hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary'

const ACCENT =
  'inline-flex min-h-[36px] items-center rounded-md bg-primary px-3 text-sm font-medium text-white transition-colors hover:bg-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2'

/** Top-right auth actions only — primary nav lives in the vertical shell. */
export default function ShellAuthBar() {
  const { status, user, signOut } = useAuth()
  const router = useRouter()
  const [signingOut, setSigningOut] = useState(false)

  return (
    <div className="flex h-14 shrink-0 items-center justify-end gap-2 border-b border-surface-border bg-surface px-6">
      {status === 'loading' ? (
        <span className="min-h-[36px] w-24" aria-hidden />
      ) : status === 'authenticated' && user ? (
        <>
          <span
            className="hidden max-w-[14rem] truncate text-sm text-surface-subtle sm:inline"
            title={user.email}
          >
            {user.email}
          </span>
          <button
            type="button"
            className={QUIET}
            disabled={signingOut}
            onClick={async () => {
              setSigningOut(true)
              try {
                await signOut()
                router.push('/')
              } finally {
                setSigningOut(false)
              }
            }}
          >
            {signingOut ? 'Signing out…' : 'Log out'}
          </button>
        </>
      ) : (
        <>
          <Link href="/signup" className={ACCENT}>
            Sign up
          </Link>
          <Link href="/login" className={QUIET}>
            Login
          </Link>
        </>
      )}
    </div>
  )
}
