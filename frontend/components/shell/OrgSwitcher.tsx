'use client'

import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/components/AuthProvider'

/** Human labels for the stored role strings. */
const ROLE_LABELS: Record<string, string> = {
  owner: 'Owner',
  admin: 'Admin',
  billing_admin: 'Billing admin',
  manager: 'Manager',
  editor: 'Editor',
  analyst: 'Analyst',
  viewer: 'Viewer',
  guest: 'Guest',
  super_admin: 'Super admin',
  support: 'Support',
}

/**
 * The organization switcher, in the app shell.
 *
 * Renders nothing at all for a user with a single organization — a solo account
 * must see no new chrome. For a multi-org (contractor) user it lists every org
 * they belong to with their role in each, and switching sets the scope the API
 * client sends (`X-Org-Id`) and reloads the identity, then lands on the dashboard
 * of the chosen org so org-scoped screens refetch under the new scope.
 */
export default function OrgSwitcher() {
  const { user, switchOrg } = useAuth()
  const router = useRouter()
  const [open, setOpen] = useState(false)
  const [switching, setSwitching] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  const organizations = user?.organizations ?? []
  const activeId = user?.organization?.id ?? null

  useEffect(() => {
    if (!open) return
    function onDocClick(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDocClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  // The whole point: one org, no switcher. Rendered unconditionally by the shell,
  // so this is the single place the "only when it matters" rule lives.
  if (organizations.length <= 1) return null

  const active = organizations.find((org) => org.id === activeId) ?? organizations[0]

  async function choose(orgId: string) {
    if (orgId === activeId) {
      setOpen(false)
      return
    }
    setSwitching(true)
    try {
      await switchOrg(orgId)
      setOpen(false)
      router.push('/dashboard')
    } finally {
      setSwitching(false)
    }
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        disabled={switching}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label="Switch organization"
        className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm text-ink-foreground/80 transition-colors hover:bg-white/5 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal disabled:opacity-60"
      >
        <span className="min-w-0 flex-1">
          <span className="block text-[11px] uppercase tracking-wide text-ink-foreground/50">
            Organization
          </span>
          <span className="block truncate font-medium text-white">
            {switching ? 'Switching…' : active.name}
          </span>
        </span>
        <svg
          viewBox="0 0 24 24"
          className="h-4 w-4 shrink-0 text-ink-foreground/60"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden
        >
          <path d="m7 15 5 5 5-5M7 9l5-5 5 5" />
        </svg>
      </button>

      {open ? (
        <ul
          role="listbox"
          aria-label="Your organizations"
          className="absolute bottom-full left-0 z-40 mb-1 max-h-[min(60vh,320px)] w-full overflow-y-auto rounded-lg border border-white/10 bg-ink py-1 shadow-lg"
        >
          {organizations.map((org) => {
            const selected = org.id === activeId
            return (
              <li key={org.id} role="option" aria-selected={selected}>
                <button
                  type="button"
                  onClick={() => choose(org.id)}
                  className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal ${
                    selected
                      ? 'bg-white/10 text-signal'
                      : 'text-ink-foreground/80 hover:bg-white/5 hover:text-white'
                  }`}
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{org.name}</span>
                    <span className="block truncate text-[11px] text-ink-foreground/60">
                      {ROLE_LABELS[org.role] ?? org.role}
                    </span>
                  </span>
                  {selected ? (
                    <svg
                      viewBox="0 0 24 24"
                      className="h-4 w-4 shrink-0"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth={2}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-label="Current organization"
                    >
                      <path d="M20 6 9 17l-5-5" />
                    </svg>
                  ) : null}
                </button>
              </li>
            )
          })}
        </ul>
      ) : null}
    </div>
  )
}
