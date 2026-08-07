'use client'

import Link from 'next/link'
import Image from 'next/image'
import { usePathname, useRouter } from 'next/navigation'
import {
  useEffect,
  useRef,
  useState,
  type FocusEvent,
  type MouseEvent,
  type ReactNode,
} from 'react'
import { useAuth } from '@/components/AuthProvider'
import { useAnalysisSession } from '@/components/AnalysisSessionProvider'
import { SECTION_ICONS } from '@/components/shell/icons'
import ShellAuthBar from '@/components/shell/ShellAuthBar'
import { useShellState } from '@/components/shell/ShellStateProvider'
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
function initialsFor(user: {
  email: string
  organization?: { name: string } | null
}): string {
  return initialsFrom(user.organization?.name ?? '', user.email.split('@')[0])
}

function sectionOverviewHref(section: ShellSection): string | null {
  if (section.href) return section.href
  const firstLive = section.items.find((item) => item.href)
  return firstLive?.href ?? null
}

/** Pointer dwell before the rail widens, and grace before it closes again.
 *
 * The open delay is what makes an icon clickable: reaching for one and clicking
 * it takes well under this, so the panel never opens over the gesture. The close
 * grace forgives a pointer that clips the rail's edge on its way down a menu. */
const EXPAND_DELAY_MS = 150
const COLLAPSE_DELAY_MS = 120

/** Dwell before an open panel is handed to a different section. */
const SWAP_DELAY_MS = 120

/** The same dwell, for a pointer that is on its way into the open panel.
 *
 * The panel sits to the right of the rail, so reaching an item near its bottom
 * means cutting diagonally across the rows underneath your own. At any human
 * speed that spends longer than SWAP_DELAY_MS on each row crossed, and every one
 * of them would take the panel away mid-reach. So a section only claims the
 * panel quickly when the pointer is not travelling toward it. */
const AIMING_DELAY_MS = 500

function withRememberedAnalysis(
  href: string,
  analysisId: string | null,
): string {
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
  const { railHovered, setRailHovered, hoveredSection, setHoveredSection } =
    useShellState()
  const pathSection = sectionFromPath(pathname)
  const [navOpen, setNavOpen] = useState(false)
  const [railFocused, setRailFocused] = useState(false)
  const [isDesktop, setIsDesktop] = useState(true)

  useEffect(() => {
    const query = window.matchMedia('(min-width: 1024px)')
    const sync = () => setIsDesktop(query.matches)
    sync()
    query.addEventListener('change', sync)
    return () => query.removeEventListener('change', sync)
  }, [])

  const expandTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const collapseTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const swapTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  /** Last pointer x inside the rail. Crossing into a row reports the new
   *  position before the next mousemove does, so this still holds the old one —
   *  which is exactly what tells us which way the pointer is going. */
  const pointer = useRef(0)

  useEffect(
    () => () => {
      if (expandTimer.current) clearTimeout(expandTimer.current)
      if (collapseTimer.current) clearTimeout(collapseTimer.current)
      if (swapTimer.current) clearTimeout(swapTimer.current)
    },
    [],
  )

  function cancelExpand() {
    if (expandTimer.current) clearTimeout(expandTimer.current)
    expandTimer.current = null
  }

  function cancelCollapse() {
    if (collapseTimer.current) clearTimeout(collapseTimer.current)
    collapseTimer.current = null
  }

  function cancelSwap() {
    if (swapTimer.current) clearTimeout(swapTimer.current)
    swapTimer.current = null
  }

  function scheduleExpand() {
    if (!isDesktop) return
    cancelCollapse()
    if (expandTimer.current) return
    expandTimer.current = setTimeout(() => {
      expandTimer.current = null
      setRailHovered(true)
    }, EXPAND_DELAY_MS)
  }

  function scheduleCollapse() {
    if (!isDesktop) return
    cancelExpand()
    cancelSwap()
    if (collapseTimer.current) return
    collapseTimer.current = setTimeout(() => {
      collapseTimer.current = null
      setRailHovered(false)
      setHoveredSection(null)
    }, COLLAPSE_DELAY_MS)
  }

  // Mobile navigation closes after a route change. On desktop an open rail and
  // its section survive the AppShell remount until the pointer actually leaves.
  useEffect(() => {
    setNavOpen(false)
    setRailFocused(false)
    cancelExpand()
    cancelCollapse()
    if (!isDesktop || !railHovered) setHoveredSection(null)
    if (!isDesktop) setRailHovered(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
  const signedIn = status === 'authenticated' && Boolean(user?.email)
  const loadingAuth = status === 'loading'
  const railExpanded = !isDesktop || railHovered || railFocused
  const panelOpen =
    railExpanded &&
    SHELL_SECTIONS.some(
      (section) => section.id === hoveredSection && section.items.length > 0,
    )

  /** Point at a section. Instant, unless it would steal an open panel. */
  function hoverSection(id: ShellSectionId, event: MouseEvent<HTMLElement>) {
    if (!isDesktop) return
    cancelSwap()
    if (hoveredSection === id) return
    if (!panelOpen) {
      setHoveredSection(id)
      return
    }
    // Rightward means heading for the panel, which is the one direction a row
    // must not read as "I want you instead".
    const aiming = event.clientX > pointer.current
    swapTimer.current = setTimeout(
      () => {
        swapTimer.current = null
        setHoveredSection(id)
      },
      aiming ? AIMING_DELAY_MS : SWAP_DELAY_MS,
    )
  }

  function onRailClick(section: ShellSection) {
    const href = sectionOverviewHref(section)
    if (!href) return
    // Reaching an icon and clicking it is a complete gesture on its own, so
    // drop the expansion the pointer had queued up on its way in.
    cancelExpand()
    cancelSwap()
    setRailFocused(false)
    router.push(withRememberedAnalysis(href, rememberedAnalysisId))
  }

  function onRailBlur(event: FocusEvent<HTMLElement>) {
    const next = event.relatedTarget
    if (!(next instanceof Node) || !event.currentTarget.contains(next)) {
      setRailFocused(false)
      setHoveredSection(null)
    }
  }

  return (
    <div className="relative flex h-[100dvh] overflow-hidden bg-surface-muted text-surface-foreground">
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
        className={`fixed inset-y-0 left-0 z-30 flex h-[100dvh] w-[260px] shrink-0 flex-col overflow-visible bg-ink text-ink-foreground transition-[transform,width,box-shadow] duration-200 ease-out lg:absolute lg:h-full lg:translate-x-0 ${
          navOpen ? 'translate-x-0' : '-translate-x-full'
        } ${
          railExpanded
            ? 'lg:w-[240px] lg:shadow-[12px_0_28px_rgba(5,20,16,0.24)]'
            : 'lg:w-[74px] lg:shadow-none'
        }`}
        aria-label="Product navigation"
        aria-hidden={!navOpen && !isDesktop ? true : undefined}
        onMouseEnter={cancelCollapse}
        onMouseLeave={scheduleCollapse}
        onMouseMove={(event) => {
          pointer.current = event.clientX
        }}
        onFocusCapture={(event) => {
          if (
            isDesktop &&
            event.target instanceof HTMLElement &&
            event.target.matches(':focus-visible')
          ) {
            setRailFocused(true)
          }
        }}
        onBlurCapture={onRailBlur}
      >
        {/* The wordmark row is deliberately inert: it neither opens the rail
            (hovering the logo is not a request for the menu) nor closes it
            (which would drop the rail to 74px under a pointer on its way up). */}
        <div className="flex h-[68px] shrink-0 items-center overflow-hidden px-[19px]">
          <Link
            href="/"
            aria-label="Yanki"
            className="flex items-center rounded-lg text-lg font-semibold tracking-tight text-signal focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal"
          >
            <Image
              src="/yanki-favicon.svg"
              alt=""
              width={36}
              height={36}
              className="h-9 w-9 shrink-0"
            />
            {railExpanded ? (
              <span className="ml-3 whitespace-nowrap">Yanki</span>
            ) : null}
          </Link>
        </div>

        {/* `lg:overflow-visible` is what lets the desktop panel escape the
            column. The scroll is still needed below `lg`, where the drawer
            lists every section's children inline. */}
        <nav
          className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto overflow-x-hidden px-2 pt-3 lg:overflow-visible"
          aria-label="Toolkits"
          onMouseEnter={scheduleExpand}
        >
          {SHELL_SECTIONS.map((section) => {
            const Icon = SECTION_ICONS[section.id]
            const selected = pathSection === section.id
            const hasMenu = section.items.length > 0
            const menuOpen =
              hasMenu &&
              (!isDesktop || (railExpanded && hoveredSection === section.id))

            return (
              <div
                key={section.id}
                className="relative"
                onMouseEnter={(event) => hoverSection(section.id, event)}
              >
                <button
                  type="button"
                  onClick={() => onRailClick(section)}
                  onFocus={() => {
                    // Keyboard arrives one row at a time, so no dwell here.
                    if (!isDesktop) return
                    cancelSwap()
                    setHoveredSection(section.id)
                  }}
                  aria-label={section.label}
                  aria-expanded={hasMenu ? menuOpen : undefined}
                  aria-controls={
                    hasMenu && (!isDesktop || menuOpen)
                      ? isDesktop
                        ? `shell-subnav-desktop-${section.id}`
                        : `shell-subnav-${section.id}`
                      : undefined
                  }
                  title={!railExpanded ? section.label : undefined}
                  className={`flex min-h-[44px] w-full items-center gap-3 overflow-hidden rounded-lg px-[17px] text-left text-sm transition-colors ${
                    selected
                      ? 'bg-white/10 text-signal shadow-[inset_3px_0_0_0_#3BD1B5]'
                      : 'text-ink-foreground/80 hover:bg-white/5 hover:text-white'
                  }`}
                >
                  <Icon className="h-5 w-5 shrink-0" />
                  {railExpanded ? (
                    <span className="min-w-0 truncate whitespace-nowrap">
                      {section.label}
                    </span>
                  ) : null}
                </button>

                {hasMenu ? (
                  <div
                    id={`shell-subnav-${section.id}`}
                    className="mb-1 ml-9 flex flex-col gap-0.5 border-l border-white/10 pl-2 lg:hidden"
                  >
                    {section.items.map((item) =>
                      item.href ? (
                        <Link
                          key={item.id}
                          href={withRememberedAnalysis(
                            item.href,
                            rememberedAnalysisId,
                          )}
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

                {/* Anchored to the row and out of the column's flow. Inline, it
                    pushed every icon below it down by the height of the open
                    menu — so the icon you were reaching for moved as you
                    reached, and swapping between sections made the whole
                    column jump. `ml-2` lands the panel flush against the
                    expanded rail, leaving no gap for the pointer to fall
                    through on its way over. */}
                {isDesktop && menuOpen ? (
                  <div
                    id={`shell-subnav-desktop-${section.id}`}
                    // Arriving here settles it. The rows crossed on the way in
                    // each queued a swap, and one of them would otherwise come
                    // due seconds later and pull the panel out from under a
                    // pointer that is already inside it.
                    onMouseEnter={cancelSwap}
                    className="absolute left-full top-0 ml-2 hidden w-[216px] flex-col gap-0.5 rounded-xl border border-white/10 bg-ink p-1.5 shadow-[12px_0_28px_rgba(5,20,16,0.24)] lg:flex"
                  >
                    {section.items.map((item) => {
                      const active = flyoutItemActive(pathname, item)
                      return item.href ? (
                        <Link
                          key={item.id}
                          href={withRememberedAnalysis(
                            item.href,
                            rememberedAnalysisId,
                          )}
                          className={`flex min-h-[36px] items-center justify-between rounded-md px-2.5 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal ${
                            active
                              ? 'bg-white/10 font-medium text-signal'
                              : 'text-ink-foreground/75 hover:bg-white/5 hover:text-white'
                          }`}
                        >
                          <span className="truncate">{item.label}</span>
                          {item.badge === 'live' ? (
                            <span className="ml-2 rounded-full bg-signal/10 px-1.5 py-0.5 text-[10px] font-medium text-signal">
                              Live
                            </span>
                          ) : null}
                        </Link>
                      ) : (
                        <span
                          key={item.id}
                          aria-disabled="true"
                          className="flex min-h-[36px] items-center justify-between gap-2 px-2.5 text-xs text-ink-foreground/40"
                        >
                          <span className="truncate">{item.label}</span>
                          <span className="rounded-full bg-white/10 px-1.5 py-0.5 text-[10px]">
                            Soon
                          </span>
                        </span>
                      )
                    })}
                  </div>
                ) : null}
              </div>
            )
          })}
        </nav>

        <div
          className="mt-auto overflow-hidden border-t border-white/10 px-[19px] py-4"
          onMouseEnter={scheduleExpand}
        >
          {loadingAuth ? (
            railExpanded ? (
              <p className="whitespace-nowrap text-xs text-ink-foreground/60">
                Checking session…
              </p>
            ) : (
              <div
                className="h-9 w-9 animate-pulse rounded-full bg-white/10"
                aria-hidden
              />
            )
          ) : signedIn ? (
            <Link
              href="/settings"
              aria-label="Open profile settings"
              title={!railExpanded ? 'Profile' : undefined}
              className="-mx-2 flex min-h-[44px] items-center gap-3 rounded-lg px-2 transition-colors hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal"
            >
              <div
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-semibold text-white"
                aria-hidden
              >
                {initialsFor(user!)}
              </div>
              {railExpanded ? (
                <div className="min-w-0 flex-1">
                  {/* The organization and role, not a guess at a name derived
                    from the email local part — which read as "aytek" for an
                    account belonging to a company. */}
                  <p className="truncate text-sm font-medium text-white">
                    {user!.organization?.name ?? user!.email}
                  </p>
                  <p className="truncate text-xs text-ink-foreground/70">
                    {user!.role
                      ? `${ROLE_LABELS[user!.role] ?? user!.role} · `
                      : ''}
                    {user!.email}
                  </p>
                </div>
              ) : null}
            </Link>
          ) : (
            <div className="flex items-center gap-3">
              <div
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white/10 text-xs font-semibold text-ink-foreground/70"
                aria-hidden
              >
                ?
              </div>
              {railExpanded ? (
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-white">
                    No user
                  </p>
                  <p className="truncate text-xs text-ink-foreground/70">
                    Not signed in
                  </p>
                </div>
              ) : null}
            </div>
          )}
        </div>
      </aside>

      <div className="relative z-0 flex min-h-0 min-w-0 flex-1 flex-col lg:ml-[74px]">
        <ShellAuthBar onOpenNav={() => setNavOpen(true)} navOpen={navOpen} />
        <main className="min-h-0 min-w-0 flex-1 overflow-y-auto">
          {children}
        </main>
      </div>
    </div>
  )
}
