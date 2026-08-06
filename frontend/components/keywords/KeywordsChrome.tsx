'use client'

import type { ReactNode } from 'react'
import Link from 'next/link'
import AppShell from '@/components/shell/AppShell'

const LOCALES = [
  { value: 'en', label: 'English (en)' },
  { value: 'en-GB', label: 'English UK (en-GB)' },
  { value: 'tr', label: 'Turkish (tr)' },
  { value: 'de', label: 'German (de)' },
  { value: 'fr', label: 'French (fr)' },
] as const

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

export function KeywordsShell({
  title,
  children,
}: {
  title: string
  children: ReactNode
}) {
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
          <Link
            href="/search-visibility/keywords"
            className="text-primary hover:text-primary-hover"
          >
            Keywords
          </Link>
          <span className="mx-1.5">/</span>
          {title}
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-semibold tracking-tight text-surface-foreground">
            {title}
          </h1>
          <EstimatedBadge />
        </div>
        <p className="mt-2 max-w-2xl text-sm text-surface-subtle">
          Open-source preview via SearXNG. Demand and difficulty scores are
          estimated proxies — not Semrush volume or KD%. Enable{' '}
          <code className="font-mono text-xs">KEYWORD_ENABLED</code> on the API.
        </p>
        <nav className="mt-4 flex gap-4 text-sm" aria-label="Keyword tools">
          <Link
            href="/search-visibility/keywords"
            className="font-medium text-primary hover:text-primary-hover"
          >
            Overview
          </Link>
          <Link
            href="/search-visibility/keywords/magic"
            className="font-medium text-primary hover:text-primary-hover"
          >
            Magic
          </Link>
        </nav>
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
