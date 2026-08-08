'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import {
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { createPortal } from 'react-dom'
import { useAuth } from '@/components/AuthProvider'
import { useAnalysisSession } from '@/components/AnalysisSessionProvider'
import { SECTION_ICONS } from '@/components/shell/icons'
import OrgSwitcher from '@/components/shell/OrgSwitcher'
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

function initialsFrom(label: string, fallback: string): string {
  const source = (label || fallback || 'yk').trim()
  const words = source.split(/[\s._-]+/).filter(Boolean)
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase()
  return source.slice(0, 2).toUpperCase()
}

/** Initials from the organization where there is one, else the email. */
function initialsFor(user: { email: string; organization?: { name: string } | null }): string {
  return initialsFrom(user.organization?.name ?? '', user.email.split('@')[0])
}

function sectionOverviewHref(section: ShellSection): string | null {
  if (section.href) return section.href
  const firstLive = section.items.find((item) => item.href)
  return firstLive?.href ?? null
}

function withRememberedAnalysis(href: string, analysisId: string | null): string {
  if (!analysisId) return href
  if (
    !href.startsWith('/ai-visibility') &&
    !href.startsWith('/search-visibility')
  ) {
    return href
  }
  if (href.includes('analysis=')) return href
  return `${href}${href.includes('?') ? '&' : '?'}analysis=${analysisId}`
}

export default function AppShell({ children }: AppShellProps) {
  const pathname = usePathname()
  const router = useRouter()
  const { status, user } = useAuth()
  const { analysisId: rememberedAnalysisId } = useAnalysisSession()
  const pathSection = sectionFromPath(pathname)
  const [hoveredSection, setHoveredSection] = useState<ShellSectionId | null>(
    null,
  )
  const [menuPos, setMenuPos] = useState<{ top: number; left: number } | null>(
    null,
  )
  const [portalReady, setPortalReady] = useState(false)
  const [navOpen, setNavOpen] = useState(false)
  // Drives two things the drawer needs and CSS cannot express: whether the
  // rail is reachable without opening it (so `aria-hidden` is not applied to
  // a visible sidebar), and whether the lateral hover flyout should exist at
  // all — hover is meaningless on a touch screen, and gating on pointer type
  // rather than width is what actually distinguishes the two.
  const [isDesktop, setIsDesktop] = useState(true)

  useEffect(() => {
    const query = window.matchMedia('(min-width: 1024px)')
    const sync = () => setIsDesktop(query.matches)
    sync()
    query.addEventListener('change', sync)
    return () => query.removeEventListener('change', sync)
  }, [])

  // Navigating closes the drawer. Without this, tapping a destination leaves
  // the overlay covering the page you just asked for.
  useEffect(() => {
    setNavOpen(false)
  }, [pathname])

  // Escape closes it, which is the one keyboard affordance a drawer must have.
  useEffect(() => {
    if (!navOpen) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setNavOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [navOpen])
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const itemRefs = useRef(new Map<ShellSectionId, HTMLElement>())

  useEffect(() => {
    setPortalReady(true)
    return () => {
      if (closeTimer.current) clearTimeout(closeTimer.current)
    }
  }, [])

  useEffect(() => {
    if (!hoveredSection) return

    function syncPosition() {
      const el = itemRefs.current.get(hoveredSection!)
      if (!el) return
      const rect = el.getBoundingClientRect()
      setMenuPos({ top: rect.top, left: rect.right + 4 })
    }

    syncPosition()
    window.addEventListener('resize', syncPosition)
    window.addEventListener('scroll', syncPosition, true)
    return () => {
      window.removeEventListener('resize', syncPosition)
      window.removeEventListener('scroll', syncPosition, true)
    }
  }, [hoveredSection])

  const signedIn = status === 'authenticated' && Boolean(user?.email)
  const loadingAuth = status === 'loading'
  const activeSection =
    SHELL_SECTIONS.find((section) => section.id === hoveredSection) ?? null

  function clearCloseTimer() {
    if (closeTimer.current) {
      clearTimeout(closeTimer.current)
      closeTimer.current = null
    }
  }

  function openHover(id: ShellSectionId) {
    clearCloseTimer()
    const el = itemRefs.current.get(id)
    if (el) {
      const rect = el.getBoundingClientRect()
      setMenuPos({ top: rect.top, left: rect.right + 4 })
    }
    setHoveredSection(id)
  }

  function scheduleCloseHover() {
    clearCloseTimer()
    closeTimer.current = setTimeout(() => {
      setHoveredSection(null)
      setMenuPos(null)
    }, HOVER_CLOSE_MS)
  }

  function onRailClick(section: ShellSection) {
    const href = sectionOverviewHref(section)
    if (href) {
      setHoveredSection(null)
      setMenuPos(null)
      router.push(withRememberedAnalysis(href, rememberedAnalysisId))
    }
  }

  const flyout =
    portalReady &&
    activeSection &&
    menuPos &&
    activeSection.items.length > 0 ? (
      <div
        role="menu"
        aria-label={activeSection.flyoutTitle ?? activeSection.label}
        className="fixed z-[200] w-[240px] rounded-lg border border-surface-border bg-surface py-2 shadow-lg"
        style={{ top: menuPos.top, left: menuPos.left }}
        onMouseEnter={clearCloseTimer}
        onMouseLeave={scheduleCloseHover}
      >
        <p className="px-3 pb-1.5 text-[11px] font-semibold uppercase tracking-wide text-surface-subtle">
          {activeSection.flyoutTitle ?? activeSection.label}
        </p>
        <div className="flex max-h-[min(70vh,420px)] flex-col gap-0.5 overflow-y-auto px-1.5">
          {activeSection.items.map((item) => {
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
                  {/* "Coming soon" says something; "N/A" only said "missing". */}
                  <span className="rounded-full bg-surface-muted px-2 py-0.5 text-[11px] font-medium text-surface-subtle">
                    Coming soon
                  </span>
                </div>
              )
            }
            return (
              <Link
                key={item.id}
                href={withRememberedAnalysis(item.href, rememberedAnalysisId)}
                role="menuitem"
                onClick={() => {
                  setHoveredSection(null)
                  setMenuPos(null)
                }}
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
    ) : null

  return (
    <div className="flex h-[100dvh] overflow-hidden bg-surface-muted text-surface-foreground">
      {/* Below `lg` the rail is an off-canvas drawer. A fixed 220px column on a
          375px screen left ~123px for content, which is not a layout so much as
          a promise that nobody opened this on a phone. */}
      {navOpen ? (
        <button
          type="button"
          aria-label="Close navigation"
          onClick={() => setNavOpen(false)}
          className="fixed inset-0 z-20 bg-black/40 lg:hidden"
        />
      ) : null}

      <aside
        id="product-nav"
        className={`fixed inset-y-0 left-0 z-30 flex h-[100dvh] w-[260px] shrink-0 flex-col bg-ink text-ink-foreground transition-transform duration-200 lg:relative lg:h-full lg:w-[220px] lg:translate-x-0 ${
          navOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
        aria-label="Product navigation"
        aria-hidden={!navOpen && !isDesktop ? true : undefined}
      >
        <div className="px-5 pb-4 pt-5">
          <Link
            href="/"
            className="text-lg font-semibold tracking-tight text-signal focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal"
          >
            Yanki
          </Link>
        </div>

        <nav
          className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto px-2"
          aria-label="Toolkits"
        >
          {SHELL_SECTIONS.map((section) => {
            const Icon = SECTION_ICONS[section.id]
            const selected = pathSection === section.id
            const hasMenu = section.items.length > 0
            const menuOpen = hoveredSection === section.id && hasMenu

            return (
              <div
                key={section.id}
                ref={(node) => {
                  if (node) itemRefs.current.set(section.id, node)
                  else itemRefs.current.delete(section.id)
                }}
                onMouseEnter={() => {
                  if (hasMenu && isDesktop) openHover(section.id)
                }}
                onMouseLeave={() => {
                  if (hasMenu && isDesktop) scheduleCloseHover()
                }}
              >
                <button
                  type="button"
                  onClick={() => onRailClick(section)}
                  onFocus={() => {
                    if (hasMenu && isDesktop) openHover(section.id)
                  }}
                  aria-haspopup={hasMenu ? 'menu' : undefined}
                  aria-expanded={hasMenu ? menuOpen : undefined}
                  className={`flex w-full min-h-[44px] items-center gap-3 rounded-lg px-3 text-left text-sm transition-colors ${
                    selected
                      ? 'bg-white/10 text-signal shadow-[inset_3px_0_0_0_#3BD1B5]'
                      : 'text-ink-foreground/80 hover:bg-white/5 hover:text-white'
                  }`}
                >
                  <Icon className="h-5 w-5 shrink-0" />
                  <span className="truncate">{section.label}</span>
                </button>

                {/* On touch the lateral flyout is unreachable, so the section's
                    destinations are listed in place instead. Desktop keeps the
                    flyout and hides this. */}
                {hasMenu ? (
                  <div className="mb-1 ml-9 flex flex-col gap-0.5 lg:hidden">
                    {section.items.map((item) =>
                      item.href ? (
                        <Link
                          key={item.id}
                          href={withRememberedAnalysis(item.href, rememberedAnalysisId)}
                          className="flex min-h-[44px] items-center rounded-md px-2 text-sm text-ink-foreground/80 hover:bg-white/5 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal"
                        >
                          {item.label}
                        </Link>
                      ) : (
                        <span
                          key={item.id}
                          aria-disabled="true"
                          className="flex min-h-[44px] items-center gap-2 px-2 text-sm text-ink-foreground/40"
                        >
                          {item.label}
                          <span className="rounded-full bg-white/10 px-2 py-0.5 text-[11px]">
                            Coming soon
                          </span>
                        </span>
                      ),
                    )}
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
            <div className="space-y-2">
              {/* Only rendered for a user with more than one organization; a
                  solo account gets no extra chrome here. */}
              <OrgSwitcher />
              <div className="flex items-center gap-3">
                <div
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-semibold text-white"
                  aria-hidden
                >
                  {initialsFor(user!)}
                </div>
                <div className="min-w-0 flex-1">
                  {/* The organization and role, not a guess at a name derived
                      from the email local part — which read as "aytek" for an
                      account belonging to a company. */}
                  <p className="truncate text-sm font-medium text-white">
                    {user!.organization?.name ?? user!.email}
                  </p>
                  <p className="truncate text-xs text-ink-foreground/70">
                    {user!.role ? `${ROLE_LABELS[user!.role] ?? user!.role} · ` : ''}
                    {user!.email}
                  </p>
                </div>
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

      <div className="relative z-0 flex min-h-0 min-w-0 flex-1 flex-col">
        <ShellAuthBar onOpenNav={() => setNavOpen(true)} navOpen={navOpen} />
        <main className="min-h-0 min-w-0 flex-1 overflow-y-auto">{children}</main>
      </div>

      {flyout && isDesktop ? createPortal(flyout, document.body) : null}
    </div>
  )
}
