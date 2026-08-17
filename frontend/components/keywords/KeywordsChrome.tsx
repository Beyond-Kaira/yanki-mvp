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
import ISO6391 from 'iso-639-1'
import localeEmoji from 'locale-emoji'
import AppShell from '@/components/shell/AppShell'

/** Every ISO 639-1 language, as `{ code: 'tr', name: 'Turkish', nativeName: 'Türkçe' }`.
 *
 * The code is what we send as the locale: SearXNG takes it as the search
 * language, and the API's `locale_map` turns it into a Google Ads language/geo
 * pair — codes missing from that map fall back to English/US there.
 *
 * The flag is the language's CLDR default region, so it is a hint and not a
 * claim: Arabic shows 🇪🇬, and the ten languages with no region at all (Esperanto
 * and friends) fall back to a globe. */
const LOCALES = ISO6391.getLanguages(ISO6391.getAllCodes()).map((language) => ({
  ...language,
  flag: localeEmoji(language.code) || '🌐',
}))

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
 * A native `<select>` cannot style its own option list, and 183 languages need a
 * search box. This is the same button + `role="listbox"` shape the org switcher
 * already uses, so the two dropdowns in the app behave alike. */
export function KeywordLocaleSelect({
  value,
  onChange,
}: {
  value: string
  onChange: (value: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const containerRef = useRef<HTMLDivElement>(null)
  const popupRef = useRef<HTMLDivElement>(null)

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

  const active = LOCALES.find((locale) => locale.code === value) ?? LOCALES[0]
  const needle = query.trim().toLowerCase()
  // Native name included so "Türkçe" and "Deutsch" find their own language.
  const matches = needle
    ? LOCALES.filter(
        (locale) =>
          locale.name.toLowerCase().includes(needle) ||
          locale.nativeName.toLowerCase().includes(needle) ||
          locale.code.includes(needle),
      )
    : LOCALES

  function choose(next: string) {
    onChange(next)
    setOpen(false)
    setQuery('')
  }

  // Arrow keys walk the options, the way the native select did.
  function onPopupKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return
    event.preventDefault()
    const buttons = Array.from(popupRef.current?.querySelectorAll('li button') ?? [])
    if (buttons.length === 0) return
    const index = buttons.indexOf(document.activeElement as HTMLButtonElement)
    const next = event.key === 'ArrowDown' ? index + 1 : index - 1
    ;(buttons[(next + buttons.length) % buttons.length] as HTMLButtonElement).focus()
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => {
          setQuery('')
          setOpen((current) => !current)
        }}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`Locale: ${active.name}`}
        className="flex w-full items-center gap-2 rounded-lg border border-surface-border bg-surface px-3 py-2 text-left text-sm text-surface-foreground transition-colors hover:border-primary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        <span className="text-base leading-none">{active.flag}</span>
        <span className="min-w-0 flex-1 truncate font-medium">{active.name}</span>
        <span className="shrink-0 text-xs text-surface-subtle">{active.code}</span>
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
        <div
          ref={popupRef}
          onKeyDown={onPopupKeyDown}
          className="absolute left-0 top-full z-40 mt-1 w-full overflow-hidden rounded-lg border border-surface-border bg-surface shadow-lg"
        >
          <div className="border-b border-surface-border p-2">
            <input
              // eslint-disable-next-line jsx-a11y/no-autofocus -- the popup only exists once the user opened it
              autoFocus
              type="text"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              // The picker sits inside the analyze form: Enter must take the top
              // match, not submit the form underneath.
              onKeyDown={(event) => {
                if (event.key !== 'Enter') return
                event.preventDefault()
                if (matches.length > 0) choose(matches[0].code)
              }}
              placeholder="Search language…"
              aria-label="Search language"
              className="w-full rounded-md border border-surface-border bg-surface-muted px-2 py-1.5 text-sm text-surface-foreground placeholder:text-surface-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            />
          </div>
          <ul
            role="listbox"
            aria-label="Locale"
            className="max-h-64 overflow-y-auto py-1"
          >
            {matches.map((locale) => {
              const selected = locale.code === active.code
              return (
                <li key={locale.code} role="option" aria-selected={selected}>
                  <button
                    type="button"
                    onClick={() => choose(locale.code)}
                    className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary ${
                      selected
                        ? 'bg-primary/10 text-primary'
                        : 'text-surface-foreground hover:bg-surface-border/40'
                    }`}
                  >
                    <span className="text-base leading-none">{locale.flag}</span>
                    <span className="min-w-0 flex-1 truncate">
                      {locale.name}
                      {locale.nativeName !== locale.name ? (
                        <span className="text-surface-subtle"> · {locale.nativeName}</span>
                      ) : null}
                    </span>
                    <span className="shrink-0 text-xs text-surface-subtle">{locale.code}</span>
                  </button>
                </li>
              )
            })}
            {matches.length === 0 ? (
              <li className="px-3 py-2 text-sm text-surface-subtle">No match</li>
            ) : null}
          </ul>
        </div>
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
