'use client'

import type { ReactNode } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import AppShell from '@/components/shell/AppShell'

const LOCALES = [
  { value: 'en', label: 'English (en)' },
  { value: 'en-GB', label: 'English UK (en-GB)' },
  { value: 'tr', label: 'Turkish (tr)' },
  { value: 'de', label: 'German (de)' },
  { value: 'fr', label: 'French (fr)' },
] as const

const TABS = [
  { href: '/search-visibility/keywords', label: 'Overview', match: 'exact' as const },
  {
    href: '/search-visibility/keywords/magic',
    label: 'Magic',
    match: 'prefix' as const,
  },
]

export function KeywordLocaleOptions() {
  return (
    <>
      {LOCALES.map((locale) => (
        <option key={locale.value} value={locale.value}>
          {locale.label}
        </option>
      ))}
    </>
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
