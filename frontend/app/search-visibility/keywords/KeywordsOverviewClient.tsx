'use client'

import { useState } from 'react'
import { ApiError, overviewKeyword } from '@/lib/api'
import type { KeywordOverviewResponse } from '@/lib/contracts'
import {
  KeywordLocaleOptions,
  KeywordsShell,
  signalNumber,
  signalText,
} from '@/components/keywords/KeywordsChrome'

export default function KeywordsOverviewClient() {
  const [keyword, setKeyword] = useState('')
  const [locale, setLocale] = useState('en')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<KeywordOverviewResponse | null>(null)

  async function runOverview() {
    setLoading(true)
    setError(null)
    try {
      const data = await overviewKeyword({ keyword: keyword.trim(), locale })
      setResult(data)
    } catch (err) {
      setResult(null)
      setError(err instanceof ApiError ? err.message : 'Something went wrong.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <KeywordsShell title="Keyword Overview">
      <form
        onSubmit={(event) => {
          event.preventDefault()
          void runOverview()
        }}
        className="flex flex-col gap-3 rounded-2xl border border-surface-border bg-surface p-4 sm:flex-row sm:items-end"
      >
        <label className="min-w-0 flex-1 text-sm">
          <span className="mb-1 block text-surface-subtle">Keyword</span>
          <input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            required
            maxLength={120}
            placeholder="e.g. money transfer"
            className="w-full rounded-lg border border-surface-border bg-surface-elevated px-3 py-2 text-surface-foreground"
          />
        </label>
        <label className="text-sm sm:w-44">
          <span className="mb-1 block text-surface-subtle">Locale</span>
          <select
            value={locale}
            onChange={(e) => setLocale(e.target.value)}
            className="w-full rounded-lg border border-surface-border bg-surface-elevated px-3 py-2 text-surface-foreground"
          >
            <KeywordLocaleOptions />
          </select>
        </label>
        <button
          type="submit"
          disabled={loading || !keyword.trim()}
          className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-hover disabled:opacity-50"
        >
          {loading ? 'Analyzing…' : 'Analyze'}
        </button>
      </form>

      {error ? (
        <p className="mt-4 text-sm text-warning-strong" role="alert">
          {error}
        </p>
      ) : null}

      {result ? (
        <div className="mt-8 space-y-6">
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="rounded-xl border border-surface-border bg-surface p-4">
              <p className="text-xs uppercase tracking-wide text-surface-subtle">
                Intent
              </p>
              <p className="mt-1 text-lg font-semibold capitalize">
                {signalText(result.signals, 'intent')}
              </p>
            </div>
            <div className="rounded-xl border border-surface-border bg-surface p-4">
              <p className="text-xs uppercase tracking-wide text-surface-subtle">
                Est. demand
              </p>
              <p className="mt-1 text-lg font-semibold">
                {signalNumber(result.signals, 'estimated_demand_score')}
              </p>
            </div>
            <div className="rounded-xl border border-surface-border bg-surface p-4">
              <p className="text-xs uppercase tracking-wide text-surface-subtle">
                Est. difficulty
              </p>
              <p className="mt-1 text-lg font-semibold">
                {signalNumber(result.signals, 'estimated_difficulty_score')}
              </p>
              <p className="mt-1 text-xs text-surface-subtle">
                Basis: {signalText(result.signals, 'difficulty_basis')}
              </p>
            </div>
          </div>

          <section>
            <h2 className="text-lg font-semibold text-surface-foreground">
              Sample ideas
            </h2>
            <ul className="mt-3 divide-y divide-surface-border rounded-xl border border-surface-border bg-surface">
              {(result.sample_ideas ?? []).map((idea) => (
                <li
                  key={`${idea.source}:${idea.phrase}`}
                  className="flex flex-wrap items-baseline justify-between gap-2 px-4 py-3 text-sm"
                >
                  <span className="font-medium text-surface-foreground">
                    {idea.phrase}
                  </span>
                  <span className="text-xs text-surface-subtle">{idea.source}</span>
                </li>
              ))}
            </ul>
          </section>
        </div>
      ) : null}
    </KeywordsShell>
  )
}
