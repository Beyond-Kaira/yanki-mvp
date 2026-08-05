'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { useAuth } from '@/components/AuthProvider'

const QUIET =
  'inline-flex min-h-[36px] items-center rounded px-2 text-sm font-medium text-surface-subtle hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary'

const ACCENT =
  'inline-flex min-h-[36px] items-center rounded-md bg-primary px-3 text-sm font-medium text-white transition-colors hover:bg-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2'

interface ShellAuthBarProps {
  /** Opens the mobile navigation drawer. Absent on screens that show the rail. */
  onOpenNav?: () => void
  navOpen?: boolean
}

/** Top bar: the mobile nav trigger on the left, auth actions on the right. */
export default function ShellAuthBar({ onOpenNav, navOpen }: ShellAuthBarProps) {
  const { status, user, signOut } = useAuth()
  const router = useRouter()
  const [signingOut, setSigningOut] = useState(false)

  return (
    <div className="flex h-14 shrink-0 items-center gap-2 border-b border-surface-border bg-surface px-4 sm:px-6">
      {onOpenNav ? (
        <button
          type="button"
          onClick={onOpenNav}
          aria-label="Open navigation"
          aria-expanded={navOpen ?? false}
          aria-controls="product-nav"
          className="-ml-1 inline-flex h-11 w-11 items-center justify-center rounded-md text-surface-subtle hover:bg-surface-muted hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary lg:hidden"
        >
          <svg
            viewBox="0 0 24 24"
            className="h-5 w-5"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            strokeLinecap="round"
            aria-hidden
          >
            <path d="M4 7h16M4 12h16M4 17h16" />
          </svg>
        </button>
      ) : null}

      <div className="flex-1" />
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
