'use client'

import Link from 'next/link'
import { useAuth } from '@/components/AuthProvider'

const PRIMARY =
  'inline-flex min-h-[44px] items-center justify-center rounded-md bg-primary px-5 text-sm font-medium text-white transition-colors hover:bg-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2'

const SECONDARY =
  'inline-flex min-h-[44px] items-center justify-center rounded-md border border-surface-border px-5 text-sm font-medium transition-colors hover:border-primary hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary'

/**
 * The only part of the landing page that needs a session, kept apart from the
 * rest so the copy around it stays a server component and renders immediately.
 *
 * While the session resolves nothing is offered — not the signed-out pair,
 * which would flash at somebody who is in fact signed in, and not the dashboard
 * link, which would do the same in reverse. The reserved height keeps the
 * paragraphs below from jumping when the answer arrives.
 */
export function LandingHeroCta() {
  const { status } = useAuth()

  if (status === 'loading') return <div className="mt-8 min-h-[44px]" aria-hidden />

  if (status === 'authenticated') {
    return (
      <div className="mt-8">
        <Link href="/dashboard" className={PRIMARY}>
          Go to dashboard
        </Link>
      </div>
    )
  }

  return (
    <>
      <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
        <Link href="/signup" className={PRIMARY}>
          Create an account
        </Link>
        <Link href="/checker" className={SECONDARY}>
          Try the free checker
        </Link>
      </div>
      <p className="mt-3 text-sm text-surface-subtle">
        Already have an account?{' '}
        <Link href="/login" className="font-medium text-primary hover:underline">
          Log in
        </Link>
        .
      </p>
    </>
  )
}

/**
 * The closing pitch, which only makes sense to somebody who has not signed up.
 * Withheld until the session is known rather than shown and then retracted.
 */
export function LandingClosingCta() {
  const { status } = useAuth()
  if (status !== 'anonymous') return null

  return (
    <section className="mt-14 rounded-lg border border-surface-border bg-surface p-6 sm:mt-20 sm:p-8">
      <h2 className="text-xl font-semibold tracking-tight sm:text-2xl">
        See your own numbers
      </h2>
      <p className="mt-2 max-w-2xl text-sm leading-relaxed text-surface-subtle">
        Create an account to run a full analysis, track it over time, and invite your
        team. Or try the free checker first — no account needed.
      </p>
      <div className="mt-6 flex flex-col gap-3 sm:flex-row">
        <Link href="/signup" className={PRIMARY}>
          Create an account
        </Link>
        <Link href="/methodology" className={SECONDARY}>
          Read the methodology
        </Link>
      </div>
    </section>
  )
}
