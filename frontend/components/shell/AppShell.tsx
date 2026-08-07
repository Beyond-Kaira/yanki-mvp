'use client'

import Link from 'next/link'
import Image from 'next/image'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect, useState, type FocusEvent, type ReactNode } from 'react'
import { useAuth } from '@/components/AuthProvider'
import { useAnalysisSession } from '@/components/AnalysisSessionProvider'
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
  const pathSection = sectionFromPath(pathname)
  const [hoveredSection, setHoveredSection] = useState<ShellSectionId | null>(
    null,
  )
  const [navOpen, setNavOpen] = useState(false)
  const [railHovered, setRailHovered] = useState(false)
  const [railFocused, setRailFocused] = useState(false)
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
    setHoveredSection(null)
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
  const inlineSection = hoveredSection ?? pathSection

  function onRailClick(section: ShellSection) {
    const href = sectionOverviewHref(section)
    if (href) {
      setHoveredSection(null)
      setRailFocused(false)
      router.push(withRememberedAnalysis(href, rememberedAnalysisId))
    }
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
        onMouseLeave={() => {
          if (!isDesktop) return
          setRailHovered(false)
          setHoveredSection(null)
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
        <div
          className="flex h-[68px] shrink-0 items-center overflow-hidden px-[19px]"
          onMouseEnter={() => {
            if (!isDesktop) return
            setRailHovered(false)
            setHoveredSection(null)
          }}
        >
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

        <nav
          className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto overflow-x-hidden px-2 pt-3"
          aria-label="Toolkits"
          onMouseEnter={() => {
            if (isDesktop) setRailHovered(true)
          }}
        >
          {SHELL_SECTIONS.map((section) => {
            const Icon = SECTION_ICONS[section.id]
            const selected = pathSection === section.id
            const hasMenu = section.items.length > 0
            const menuOpen =
              hasMenu &&
              (!isDesktop || (railExpanded && inlineSection === section.id))

            return (
              <div
                key={section.id}
                onMouseEnter={() => {
                  if (isDesktop) setHoveredSection(section.id)
                }}
              >
                <button
                  type="button"
                  onClick={() => onRailClick(section)}
                  onFocus={() => {
                    if (isDesktop) setHoveredSection(section.id)
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

                {isDesktop && menuOpen ? (
                  <div
                    id={`shell-subnav-desktop-${section.id}`}
                    className="mb-1 ml-[27px] hidden flex-col gap-0.5 border-l border-white/10 py-1 pl-3 lg:flex"
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
                          onClick={() => {
                            setHoveredSection(null)
                            setRailFocused(false)
                          }}
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
          onMouseEnter={() => {
            if (isDesktop) setRailHovered(true)
          }}
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
            <div className="flex items-center gap-3">
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
            </div>
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
