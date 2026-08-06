'use client'

import { useState } from 'react'
import { ApiError, expandKeywords } from '@/lib/api'
import type { KeywordExpandResponse } from '@/lib/contracts'
import {
  KeywordLocaleOptions,
  KeywordsShell,
  signalNumber,
  signalText,
} from '@/components/keywords/KeywordsChrome'

export default function KeywordsMagicClient() {
  const [seed, setSeed] = useState('')
  const [locale, setLocale] = useState('en')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<KeywordExpandResponse | null>(null)

  async function runExpand() {
    setLoading(true)
    setError(null)
    try {
      const data = await expandKeywords({
        seed: seed.trim(),
        locale,
        max_ideas: 50,
      })
      setResult(data)
    } catch (err) {
      setResult(null)
      setError(err instanceof ApiError ? err.message : 'Something went wrong.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <KeywordsShell title="Keyword Magic">
      <form
        onSubmit={(event) => {
          event.preventDefault()
          void runExpand()
        }}
        className="flex flex-col gap-3 rounded-2xl border border-surface-border bg-surface p-4 sm:flex-row sm:items-end"
      >
        <label className="min-w-0 flex-1 text-sm">
          <span className="mb-1 block text-surface-subtle">Seed</span>
          <input
            value={seed}
            onChange={(e) => setSeed(e.target.value)}
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
          disabled={loading || !seed.trim()}
          className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-hover disabled:opacity-50"
        >
          {loading ? 'Expanding…' : 'Expand'}
        </button>
      </form>

      {error ? (
        <p className="mt-4 text-sm text-warning-strong" role="alert">
          {error}
        </p>
      ) : null}

      {result ? (
        <div className="mt-6 overflow-x-auto rounded-xl border border-surface-border bg-surface">
          <p className="border-b border-surface-border px-4 py-2 text-xs text-surface-subtle">
            Provider: {result.provider} · {result.ideas.length} ideas
          </p>
          <table className="min-w-full text-left text-sm">
            <thead className="bg-surface-elevated text-xs uppercase tracking-wide text-surface-subtle">
              <tr>
                <th className="px-4 py-2 font-medium">Keyword</th>
                <th className="px-4 py-2 font-medium">Source</th>
                <th className="px-4 py-2 font-medium">Intent</th>
                <th className="px-4 py-2 font-medium">Est. demand</th>
                <th className="px-4 py-2 font-medium">Est. difficulty</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border">
              {result.ideas.map((idea) => (
                <tr key={`${idea.source}:${idea.phrase}`}>
                  <td className="px-4 py-2 font-medium text-surface-foreground">
                    {idea.phrase}
                  </td>
                  <td className="px-4 py-2 text-surface-subtle">{idea.source}</td>
                  <td className="px-4 py-2 capitalize text-surface-subtle">
                    {signalText(idea.signals, 'intent')}
                  </td>
                  <td className="px-4 py-2 text-surface-subtle">
                    {signalNumber(idea.signals, 'estimated_demand_score')}
                  </td>
                  <td className="px-4 py-2 text-surface-subtle">
                    {signalNumber(idea.signals, 'estimated_difficulty_score')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </KeywordsShell>
  )
}
