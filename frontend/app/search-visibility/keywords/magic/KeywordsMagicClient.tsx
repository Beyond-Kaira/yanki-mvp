'use client'

import { useMemo } from 'react'
import { ApiError, expandKeywords, checkKeywordRanks } from '@/lib/api'
import type { KeywordRankHit } from '@/lib/contracts'
import {
  KeywordLocaleOptions,
  signalNumber,
  signalText,
} from '@/components/keywords/KeywordsChrome'
import { useKeywordsSession } from '@/components/keywords/KeywordsSessionProvider'

type RankByQuery = Record<string, KeywordRankHit>

export default function KeywordsMagicClient() {
  const {
    magicQuery,
    setMagicQuery,
    locale,
    setLocale,
    domain,
    setDomain,
    magicLoading,
    setMagicLoading,
    rankLoading,
    setRankLoading,
    magicError,
    setMagicError,
    magicResult,
    setMagicResult,
    selected,
    togglePhrase,
    toggleAllPhrases,
    ranks,
    mergeRanks,
    clearMagicSelection,
  } = useKeywordsSession()

  const ideaKeys = useMemo(
    () => (magicResult?.ideas ?? []).map((idea) => idea.phrase),
    [magicResult],
  )

  async function runExpand() {
    setMagicLoading(true)
    setMagicError(null)
    clearMagicSelection()
    try {
      const data = await expandKeywords({
        seed: magicQuery.trim(),
        locale,
        max_ideas: 50,
      })
      setMagicResult(data)
    } catch (err) {
      setMagicResult(null)
      setMagicError(
        err instanceof ApiError ? err.message : 'Something went wrong.',
      )
    } finally {
      setMagicLoading(false)
    }
  }

  async function runRankCheck() {
    if (!domain.trim() || selected.size === 0) return
    setRankLoading(true)
    setMagicError(null)
    try {
      const data = await checkKeywordRanks({
        domain: domain.trim(),
        queries: Array.from(selected),
        locale,
      })
      const next: RankByQuery = {}
      for (const row of data.results) {
        next[row.query] = row
      }
      mergeRanks(next)
    } catch (err) {
      setMagicError(
        err instanceof ApiError ? err.message : 'Something went wrong.',
      )
    } finally {
      setRankLoading(false)
    }
  }

  function rankLabel(phrase: string): string {
    const hit = ranks[phrase]
    if (!hit) return '—'
    if (!hit.measurable) return 'n/a'
    if (hit.appeared) return hit.rank != null ? `#${hit.rank}` : 'yes'
    return 'no'
  }

  return (
    <>
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
            value={magicQuery}
            onChange={(e) => setMagicQuery(e.target.value)}
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
          disabled={magicLoading || !magicQuery.trim()}
          className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-hover disabled:opacity-50"
        >
          {magicLoading ? 'Expanding…' : 'Expand'}
        </button>
      </form>

      {magicError ? (
        <p className="mt-4 text-sm text-warning-strong" role="alert">
          {magicError}
        </p>
      ) : null}

      {magicResult ? (
        <div className="mt-6 space-y-4">
          <div className="flex flex-col gap-3 rounded-2xl border border-surface-border bg-surface p-4 sm:flex-row sm:items-end">
            <label className="min-w-0 flex-1 text-sm">
              <span className="mb-1 block text-surface-subtle">
                Your domain (rank check)
              </span>
              <input
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                placeholder="example.com"
                className="w-full rounded-lg border border-surface-border bg-surface-elevated px-3 py-2 text-surface-foreground"
              />
            </label>
            <button
              type="button"
              disabled={rankLoading || !domain.trim() || selected.size === 0}
              onClick={() => void runRankCheck()}
              className="rounded-lg border border-surface-border px-4 py-2 text-sm font-medium text-surface-foreground hover:bg-surface-elevated disabled:opacity-50"
            >
              {rankLoading
                ? 'Checking…'
                : `Check ranks (${selected.size})`}
            </button>
          </div>

          <div className="overflow-x-auto rounded-xl border border-surface-border bg-surface">
            <p className="border-b border-surface-border px-4 py-2 text-xs text-surface-subtle">
              Provider: {magicResult.provider} · {magicResult.ideas.length}{' '}
              ideas · select rows then check own-domain rank (max ~10 queries)
            </p>
            <table className="min-w-full text-left text-sm">
              <thead className="bg-surface-elevated text-xs uppercase tracking-wide text-surface-subtle">
                <tr>
                  <th className="px-4 py-2 font-medium">
                    <input
                      type="checkbox"
                      aria-label="Select all"
                      checked={
                        ideaKeys.length > 0 && selected.size === ideaKeys.length
                      }
                      onChange={() => toggleAllPhrases(ideaKeys)}
                    />
                  </th>
                  <th className="px-4 py-2 font-medium">Keyword</th>
                  <th className="px-4 py-2 font-medium">Source</th>
                  <th className="px-4 py-2 font-medium">Intent</th>
                  <th className="px-4 py-2 font-medium">Volume</th>
                  <th className="px-4 py-2 font-medium">Est. demand</th>
                  <th className="px-4 py-2 font-medium">Est. difficulty</th>
                  <th className="px-4 py-2 font-medium">Our rank</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-border">
                {magicResult.ideas.map((idea) => (
                  <tr key={`${idea.source}:${idea.phrase}`}>
                    <td className="px-4 py-2">
                      <input
                        type="checkbox"
                        checked={selected.has(idea.phrase)}
                        onChange={() => togglePhrase(idea.phrase)}
                        aria-label={`Select ${idea.phrase}`}
                      />
                    </td>
                    <td className="px-4 py-2 font-medium text-surface-foreground">
                      {idea.phrase}
                    </td>
                    <td className="px-4 py-2 text-surface-subtle">{idea.source}</td>
                    <td className="px-4 py-2 capitalize text-surface-subtle">
                      {signalText(idea.signals, 'intent')}
                    </td>
                    <td className="px-4 py-2 text-surface-subtle">
                      {signalNumber(idea.signals, 'volume')}
                    </td>
                    <td className="px-4 py-2 text-surface-subtle">
                      {signalNumber(idea.signals, 'estimated_demand_score')}
                    </td>
                    <td className="px-4 py-2 text-surface-subtle">
                      {signalNumber(idea.signals, 'estimated_difficulty_score')}
                    </td>
                    <td className="px-4 py-2 text-surface-subtle">
                      {rankLabel(idea.phrase)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </>
  )
}
