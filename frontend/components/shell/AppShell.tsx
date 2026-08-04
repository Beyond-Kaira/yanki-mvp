'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import {
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { useAuth } from '@/components/AuthProvider'
import { SECTION_ICONS } from '@/components/shell/icons'
import ShellAuthBar from '@/components/shell/ShellAuthBar'
import {
  SHELL_SECTIONS,
  flyoutItemActive,
  sectionFromPath,
  type ShellSection,
  type ShellSectionId,
} from '@/lib/shell-nav'

interface AppShellProps {
  children: ReactNode
}

const HOVER_CLOSE_MS = 180

function initialsFromEmail(email: string): string {
  const local = email.split('@')[0] || 'yk'
  const parts = local.split(/[._-]/).filter(Boolean)
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase()
  }
  return local.slice(0, 2).toUpperCase()
}

function sectionOverviewHref(section: ShellSection): string | null {
  if (section.href) return section.href
  const firstLive = section.items.find((item) => item.href)
  return firstLive?.href ?? null
}

export default function AppShell({ children }: AppShellProps) {
  const pathname = usePathname()
  const router = useRouter()
  const { status, user } = useAuth()
  const pathSection = sectionFromPath(pathname)
  const [hoveredSection, setHoveredSection] = useState<ShellSectionId | null>(
    null,
  )
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (closeTimer.current) clearTimeout(closeTimer.current)
    }
  }, [])

  const signedIn = status === 'authenticated' && Boolean(user?.email)
  const loadingAuth = status === 'loading'

  function clearCloseTimer() {
    if (closeTimer.current) {
      clearTimeout(closeTimer.current)
      closeTimer.current = null
    }
  }

  function openHover(id: ShellSectionId) {
    clearCloseTimer()
    setHoveredSection(id)
  }

  function scheduleCloseHover() {
    clearCloseTimer()
    closeTimer.current = setTimeout(() => {
      setHoveredSection(null)
    }, HOVER_CLOSE_MS)
  }

  function onRailClick(section: ShellSection) {
    const href = sectionOverviewHref(section)
    if (href) {
      setHoveredSection(null)
      router.push(href)
    }
  }

  return (
    <div className="flex min-h-screen bg-surface-muted text-surface-foreground">
      <aside
        className="relative z-30 flex w-[220px] shrink-0 flex-col bg-ink text-ink-foreground"
        aria-label="Product navigation"
      >
        <div className="px-5 pb-4 pt-5">
          <Link
            href="/"
            className="text-lg font-semibold tracking-tight text-signal focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal"
          >
            Yanki
          </Link>
        </div>

        <nav className="flex flex-1 flex-col gap-0.5 px-2" aria-label="Toolkits">
          {SHELL_SECTIONS.map((section) => {
            const Icon = SECTION_ICONS[section.id]
            const selected = pathSection === section.id
            const hasMenu = section.items.length > 0
            const menuOpen = hoveredSection === section.id && hasMenu

            return (
              <div
                key={section.id}
                className="relative"
                onMouseEnter={() => {
                  if (hasMenu) openHover(section.id)
                }}
                onMouseLeave={() => {
                  if (hasMenu) scheduleCloseHover()
                }}
              >
                <button
                  type="button"
                  onClick={() => onRailClick(section)}
                  onFocus={() => {
                    if (hasMenu) openHover(section.id)
                  }}
                  aria-haspopup={hasMenu ? 'menu' : undefined}
                  aria-expanded={hasMenu ? menuOpen : undefined}
                  className={`flex w-full min-h-[40px] items-center gap-3 rounded-lg px-3 text-left text-sm transition-colors ${
                    selected
                      ? 'bg-white/10 text-signal shadow-[inset_3px_0_0_0_#3BD1B5]'
                      : 'text-ink-foreground/80 hover:bg-white/5 hover:text-white'
                  }`}
                >
                  <Icon className="h-5 w-5 shrink-0" />
                  <span className="truncate">{section.label}</span>
                </button>

                {menuOpen ? (
                  <div
                    role="menu"
                    aria-label={section.flyoutTitle ?? section.label}
                    className="absolute left-full top-0 z-50 ml-1 w-[240px] rounded-lg border border-surface-border bg-surface py-2 shadow-lg"
                    onMouseEnter={clearCloseTimer}
                    onMouseLeave={scheduleCloseHover}
                  >
                    <p className="px-3 pb-1.5 text-[11px] font-semibold uppercase tracking-wide text-surface-subtle">
                      {section.flyoutTitle ?? section.label}
                    </p>
                    <div className="flex flex-col gap-0.5 px-1.5">
                      {section.items.map((item) => {
                        const active = flyoutItemActive(pathname, item)
                        if (!item.href) {
                          return (
                            <div
                              key={item.id}
                              role="menuitem"
                              aria-disabled="true"
                              className="flex min-h-[36px] items-center justify-between rounded-md px-2.5 text-sm text-surface-subtle"
                            >
                              <span>{item.label}</span>
                              <span className="rounded-full bg-surface-muted px-2 py-0.5 text-[11px] font-medium text-surface-subtle">
                                N/A
                              </span>
                            </div>
                          )
                        }
                        return (
                          <Link
                            key={item.id}
                            href={item.href}
                            role="menuitem"
                            onClick={() => setHoveredSection(null)}
                            className={`flex min-h-[36px] items-center justify-between rounded-md px-2.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
                              active
                                ? 'bg-primary-soft font-medium text-primary-strong'
                                : 'text-surface-foreground hover:bg-surface-muted'
                            }`}
                          >
                            <span>{item.label}</span>
                            {item.badge === 'live' ? (
                              <span className="rounded-full bg-success-soft px-2 py-0.5 text-[11px] font-medium text-success-strong">
                                Live
                              </span>
                            ) : null}
                          </Link>
                        )
                      })}
                    </div>
                  </div>
                ) : null}
              </div>
            )
          })}
        </nav>

        <div className="mt-auto border-t border-white/10 px-3 py-4">
          {loadingAuth ? (
            <p className="px-1 text-xs text-ink-foreground/60">Checking session…</p>
          ) : signedIn ? (
            <div className="flex items-center gap-3">
              <div
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-semibold text-white"
                aria-hidden
              >
                {initialsFromEmail(user!.email)}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-white">
                  {user!.email.split('@')[0]}
                </p>
                <p className="truncate text-xs text-ink-foreground/70">
                  {user!.email}
                </p>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-3">
              <div
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white/10 text-xs font-semibold text-ink-foreground/70"
                aria-hidden
              >
                ?
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-white">No user</p>
                <p className="truncate text-xs text-ink-foreground/70">
                  Not signed in
                </p>
              </div>
            </div>
          )}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <ShellAuthBar />
        <main className="min-w-0 flex-1 overflow-auto">{children}</main>
      </div>
    </div>
  )
}
