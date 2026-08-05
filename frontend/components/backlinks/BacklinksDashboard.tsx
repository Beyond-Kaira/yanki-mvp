'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { useAuth } from '@/components/AuthProvider'
import { listSeoProjects } from '@/lib/api'
import type { SeoProject } from '@/lib/contracts'

/** Project picker for backlinks.
 *
 * A backlink profile belongs to a project's domain, and projects are already
 * created in Site Audit — so this deliberately does NOT offer a second "create
 * project" flow. Two front doors to one entity is how a customer ends up with
 * two projects for the same domain and a split profile.
 */
export default function BacklinksDashboard() {
  const { status } = useAuth()
  const [projects, setProjects] = useState<SeoProject[]>([])
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (status !== 'authenticated') return
    const controller = new AbortController()
    let cancelled = false
    setState('loading')

    listSeoProjects(controller.signal)
      .then((result) => {
        if (cancelled) return
        setProjects(result)
        setState('ready')
      })
      .catch((error: unknown) => {
        if (cancelled || (error instanceof Error && error.name === 'AbortError')) {
          return
        }
        setMessage(
          error instanceof Error ? error.message : 'Projects could not be loaded.',
        )
        setState('error')
      })

    return () => {
      cancelled = true
      controller.abort()
    }
  }, [status])

  if (status === 'loading') {
    return (
      <Shell>
        <p role="status" className="text-sm text-surface-subtle">
          Checking your session…
        </p>
      </Shell>
    )
  }

  if (status === 'anonymous') {
    return (
      <Shell>
        <section className="rounded-xl border border-surface-border bg-surface p-8 shadow-sm">
          <h1 className="text-2xl font-semibold text-surface-foreground">
            Sign in to view backlinks
          </h1>
          <Link
            href="/login"
            className="mt-5 inline-flex min-h-[44px] items-center rounded-md bg-primary px-5 text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            Sign in
          </Link>
        </section>
      </Shell>
    )
  }

  return (
    <Shell>
      <header>
        <h1 className="text-3xl font-semibold text-surface-foreground">
          Backlinks
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-surface-subtle">
          Who links to your domain, what changed since last time, and which
          domains your competitors have that you do not.
        </p>
      </header>

      {state === 'loading' ? (
        <p role="status" className="mt-8 text-sm text-surface-subtle">
          Loading projects…
        </p>
      ) : state === 'error' ? (
        <section
          role="alert"
          className="mt-8 rounded-xl border border-danger bg-danger-soft p-6"
        >
          <h2 className="font-semibold text-danger-strong">
            Projects could not be loaded
          </h2>
          <p className="mt-1 text-sm text-surface-foreground">{message}</p>
        </section>
      ) : !projects.length ? (
        <section className="mt-8 rounded-xl border border-surface-border bg-surface p-8 shadow-sm">
          <h2 className="text-xl font-semibold text-surface-foreground">
            No projects yet
          </h2>
          <p className="mt-2 text-sm text-surface-subtle">
            Backlinks are tracked per project domain. Create one in Site Audit and
            it will appear here.
          </p>
          <Link
            href="/site-audit"
            className="mt-5 inline-flex min-h-[44px] items-center rounded-md bg-primary px-5 text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            Go to Site Audit
          </Link>
        </section>
      ) : (
        <ul className="mt-8 grid gap-3 sm:grid-cols-2">
          {projects.map((project) => (
            <li key={project.id}>
              <Link
                href={`/backlinks/${project.id}`}
                className="block rounded-xl border border-surface-border bg-surface p-5 shadow-sm transition-colors hover:bg-surface-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              >
                <span className="block font-semibold text-surface-foreground">
                  {project.name}
                </span>
                <span className="mt-1 block truncate text-sm text-surface-subtle">
                  {project.domain}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Shell>
  )
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto max-w-6xl px-4 pb-7 pt-4 sm:px-8 sm:pb-8 sm:pt-5">
      {children}
    </main>
  )
}
