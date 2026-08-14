'use client'

import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import AppShell from '@/components/shell/AppShell'

const LOCALES = [
  { value: 'en', flag: '🇺🇸', name: 'English' },
  { value: 'en-GB', flag: '🇬🇧', name: 'English UK' },
  { value: 'tr', flag: '🇹🇷', name: 'Turkish' },
  { value: 'de', flag: '🇩🇪', name: 'German' },
  { value: 'fr', flag: '🇫🇷', name: 'French' },
] as const

const TABS = [
  { href: '/search-visibility/keywords', label: 'Overview', match: 'exact' as const },
  {
    href: '/search-visibility/keywords/magic',
    label: 'Magic',
    match: 'prefix' as const,
  },
]

/** Locale picker for Overview + Magic.
 *
 * A native `<select>` cannot style its own option list — the flags landed in a
 * plain OS dropdown. This is the same button + `role="listbox"` shape the org
 * switcher already uses, so the two dropdowns in the app behave alike. */
export function KeywordLocaleSelect({
  value,
  onChange,
}: {
  value: string
  onChange: (value: string) => void
}) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLUListElement>(null)

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

  const active = LOCALES.find((locale) => locale.value === value) ?? LOCALES[0]

  // Arrow keys walk the options, the way the native select did.
  function onListKeyDown(event: ReactKeyboardEvent<HTMLUListElement>) {
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return
    event.preventDefault()
    const buttons = Array.from(listRef.current?.querySelectorAll('button') ?? [])
    const index = buttons.indexOf(document.activeElement as HTMLButtonElement)
    const next = event.key === 'ArrowDown' ? index + 1 : index - 1
    buttons[(next + buttons.length) % buttons.length]?.focus()
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`Locale: ${active.name}`}
        className="flex w-full items-center gap-2 rounded-lg border border-surface-border bg-surface-elevated px-3 py-2 text-left text-sm text-surface-foreground transition-colors hover:border-primary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        <span className="text-base leading-none">{active.flag}</span>
        <span className="min-w-0 flex-1 truncate font-medium">{active.name}</span>
        <span className="shrink-0 text-xs text-surface-subtle">{active.value}</span>
        <svg
          viewBox="0 0 24 24"
          className={`h-4 w-4 shrink-0 text-surface-subtle transition-transform ${open ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>

      {open ? (
        <ul
          ref={listRef}
          role="listbox"
          aria-label="Locale"
          onKeyDown={onListKeyDown}
          className="absolute left-0 top-full z-40 mt-1 w-full overflow-hidden rounded-lg border border-surface-border bg-surface-elevated py-1 shadow-lg"
        >
          {LOCALES.map((locale) => {
            const selected = locale.value === active.value
            return (
              <li key={locale.value} role="option" aria-selected={selected}>
                <button
                  type="button"
                  onClick={() => {
                    onChange(locale.value)
                    setOpen(false)
                  }}
                  className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary ${
                    selected
                      ? 'bg-primary/10 text-primary'
                      : 'text-surface-foreground hover:bg-surface-border/40'
                  }`}
                >
                  <span className="text-base leading-none">{locale.flag}</span>
                  <span className="min-w-0 flex-1 truncate">{locale.name}</span>
                  <span className="shrink-0 text-xs text-surface-subtle">{locale.value}</span>
                </button>
              </li>
            )
          })}
        </ul>
      ) : null}
    </div>
  )
}

export function EstimatedBadge() {
  return (
    <span className="inline-flex items-center rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-800 dark:text-amber-200">
      Estimated · preview
    </span>
  )
}

function KeywordsTabs() {
  const pathname = usePathname()

  return (
    <nav className="mt-6 border-b border-surface-border" aria-label="Keyword tools">
      <div className="flex gap-6">
        {TABS.map((tab) => {
          const active =
            tab.match === 'exact'
              ? pathname === tab.href
              : pathname === tab.href || pathname.startsWith(`${tab.href}/`)
          return (
            <Link
              key={tab.href}
              href={tab.href}
              aria-current={active ? 'page' : undefined}
              className={
                active
                  ? '-mb-px border-b-2 border-primary pb-2.5 text-sm font-medium text-surface-foreground'
                  : '-mb-px border-b-2 border-transparent pb-2.5 text-sm text-surface-subtle hover:text-surface-foreground'
              }
            >
              {tab.label}
            </Link>
          )
        })}
      </div>
    </nav>
  )
}

/** Shared chrome for Overview + Magic. Tab state lives in the keywords layout. */
export function KeywordsShell({ children }: { children: ReactNode }) {
  return (
    <AppShell>
      <div className="mx-auto max-w-5xl px-6 py-8 sm:px-8">
        <p className="text-sm text-surface-subtle">
          <Link
            href="/search-visibility"
            className="text-primary hover:text-primary-hover"
          >
            Search Visibility
          </Link>
          <span className="mx-1.5">/</span>
          <span className="text-surface-foreground">Keywords</span>
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-semibold tracking-tight text-surface-foreground">
            Keyword Research
          </h1>
          <EstimatedBadge />
        </div>
        <p className="mt-2 max-w-2xl text-sm text-surface-subtle">
          Open-source preview via SearXNG. Demand and difficulty scores are
          estimated proxies — not Semrush volume or KD%. Enable{' '}
          <code className="font-mono text-xs">KEYWORD_ENABLED</code> on the API.
        </p>
        <KeywordsTabs />
        <div className="mt-6">{children}</div>
      </div>
    </AppShell>
  )
}

export function signalNumber(signals: Record<string, unknown> | undefined, key: string): string {
  const value = signals?.[key]
  return typeof value === 'number' ? String(value) : '—'
}

export function signalText(signals: Record<string, unknown> | undefined, key: string): string {
  const value = signals?.[key]
  return typeof value === 'string' && value ? value : '—'
}
