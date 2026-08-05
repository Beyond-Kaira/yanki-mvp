'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import type { ReactNode } from 'react'
import AppShell from '@/components/shell/AppShell'
import RequireAuth from '@/components/RequireAuth'
import { useAuth } from '@/components/AuthProvider'
import { ADMIN_PANEL_TABS } from '@/lib/shell-nav'

/**
 * The Admin Panel — one heading, one set of tabs, three pages beneath it.
 *
 * The layout owns the identity so every sub-page reads as part of the same
 * surface rather than three unrelated screens that happen to share a URL
 * prefix. It also owns the two guards a governance surface needs.
 *
 * **The gate is the shell, not the data.** `RequireAuth` keeps a signed-out
 * visitor from seeing the panel at all; every endpoint underneath enforces its
 * own permission independently, so someone who skips the UI still gets a 403.
 *
 * **A tab the caller cannot use is not shown.** The permission list on
 * `/auth/me` is for rendering only — hiding the audit tab from an Analyst is a
 * courtesy that saves them a dead end, not a security boundary.
 */
const TAB_PERMISSION: Record<string, string> = {
  members: 'member:read',
  invitations: 'member:read',
  audit: 'audit:read',
}

export default function AdminPanelChrome({ children }: { children: ReactNode }) {
  return (
    <RequireAuth>
      <AppShell>
        <PanelHeader>{children}</PanelHeader>
      </AppShell>
    </RequireAuth>
  )
}

function PanelHeader({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const { user } = useAuth()
  const permissions = user?.permissions ?? []

  const tabs = ADMIN_PANEL_TABS.filter((tab) => {
    const needed = TAB_PERMISSION[tab.id]
    // Before /auth/me has answered, show everything rather than flashing an
    // empty tab strip that then fills in.
    return !needed || permissions.length === 0 || permissions.includes(needed)
  })

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
      <header className="mb-6">
        <nav aria-label="Breadcrumb" className="mb-2">
          <ol className="flex items-center gap-2 text-xs text-surface-subtle">
            <li>
              <Link
                href="/dashboard"
                className="hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              >
                Home
              </Link>
            </li>
            <li aria-hidden>/</li>
            <li aria-current="page" className="font-medium text-surface-foreground">
              Admin Panel
            </li>
          </ol>
        </nav>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Admin Panel</h1>
        <p className="mt-1 text-sm text-surface-subtle">
          {user?.organization?.name
            ? `Governance for ${user.organization.name}: who is here, who is invited, and what everybody did.`
            : 'Who is here, who is invited, and what everybody did.'}
        </p>
      </header>

      <nav aria-label="Admin Panel sections" className="mb-6 border-b border-surface-border">
        <ul className="-mb-px flex gap-1 overflow-x-auto">
          {tabs.map((tab) => {
            // `/admin` must not light up on `/admin/audit`, so the root tab
            // matches exactly while the others match their subtree.
            const active =
              tab.href === '/admin'
                ? pathname === '/admin' || pathname === '/admin/'
                : pathname === tab.href || pathname.startsWith(`${tab.href}/`)
            return (
              <li key={tab.id}>
                <Link
                  href={tab.href}
                  aria-current={active ? 'page' : undefined}
                  className={`inline-flex min-h-[44px] items-center whitespace-nowrap border-b-2 px-4 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
                    active
                      ? 'border-primary font-medium text-primary-strong'
                      : 'border-transparent text-surface-subtle hover:text-surface-foreground'
                  }`}
                >
                  {tab.label}
                </Link>
              </li>
            )
          })}
        </ul>
      </nav>

      {children}
    </div>
  )
}
