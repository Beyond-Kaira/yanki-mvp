'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { useAuth } from '@/components/AuthProvider'

// Quiet nav link. `order-*` only matters on a phone, where the nav is a 2x2
// grid; at `sm` it returns to a single row in document order.
const QUIET =
  'inline-flex min-h-[40px] items-center justify-self-end rounded px-2 text-sm font-medium text-surface-subtle hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary sm:order-none'

// The one nav item that asks for something, so it carries the button treatment
// while the rest stay quiet links.
const ACCENT =
  'inline-flex min-h-[40px] items-center justify-self-end rounded-md bg-primary px-3 text-sm font-medium text-white transition-colors hover:bg-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 sm:order-none'

// Slim, additive site header rendered on every page above the routed content.
// Brand rules from brandkit v2: surface (white) bar, surface-border bottom
// hairline, one accent. Nav targets are >=40px tall with visible focus rings.
//
// A client component because the right-hand side depends on who is signed in.
export default function SiteHeader() {
  return (
    <header className="border-b border-surface-border bg-surface">
      <div className="mx-auto flex max-w-4xl items-center justify-between gap-4 px-4 py-3 sm:px-8">
        {/* shrink-0: with four nav items the row runs out of width on a phone,
            and without this the flex container compresses the logo instead of
            wrapping the nav. */}
        <Link
          href="/"
          className="inline-flex shrink-0 items-center rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          {/* Plain img: byte-identical brand SVG, no next/image loader needed. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/yanki-logo-horizontal.svg"
            alt="Yanki"
            width={125}
            height={32}
            className="h-8 w-auto"
          />
        </Link>
        {/* Phone: a 2x2 grid, so the two actions share the first row and the
            reference links sit under them. At `sm` it is a single row. */}
        <nav
          aria-label="Primary"
          className="grid grid-cols-2 items-center gap-x-1 gap-y-1 whitespace-nowrap sm:flex sm:gap-x-2"
        >
          <Link href="/checker" className={`order-1 ${QUIET}`}>
            Free checker
          </Link>
          <Link href="/methodology" className={`order-4 ${QUIET}`}>
            Methodology
          </Link>
          <AuthNav />
        </nav>
      </div>
    </header>
  )
}

function AuthNav() {
  const { status, user, signOut } = useAuth()
  const router = useRouter()
  const [signingOut, setSigningOut] = useState(false)

  // While the session is being restored the honest answer is "not known yet".
  // Rendering the signed-out pair here would flash the wrong state at anyone who
  // is in fact signed in, on every page load. The placeholders hold both grid
  // cells so the rest of the nav does not jump when the answer arrives.
  if (status === 'loading') {
    return (
      <>
        <span className="order-2 min-h-[40px]" aria-hidden="true" />
        <span className="order-3 min-h-[40px]" aria-hidden="true" />
      </>
    )
  }

  if (status === 'authenticated' && user) {
    return (
      <>
        <button
          type="button"
          className={`order-2 ${QUIET}`}
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
          Log out
        </button>
        {/* The address is the account's only identifying field today: the user
            model carries id, email and created_at, nothing else. Hidden on a
            phone, where the row has no width for it. */}
        <span
          className="order-3 hidden max-w-[12rem] justify-self-end truncate px-2 text-sm text-surface-subtle sm:inline-block"
          title={user.email}
        >
          {user.email}
        </span>
      </>
    )
  }

  return (
    <>
      <Link href="/signup" className={`order-2 ${ACCENT}`}>
        Sign up
      </Link>
      <Link href="/login" className={`order-3 ${QUIET}`}>
        Login
      </Link>
    </>
  )
}
