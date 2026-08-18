'use client'

import { ApiError, overviewKeyword } from '@/lib/api'
import {
  KeywordLanguageSelect,
  signalNumber,
  signalText,
} from '@/components/keywords/KeywordsChrome'
import { useKeywordsSession } from '@/components/keywords/KeywordsSessionProvider'

export default function KeywordsOverviewClient() {
  const {
    overviewQuery,
    setOverviewQuery,
    language,
    setLanguage,
    overviewLoading,
    setOverviewLoading,
    overviewError,
    setOverviewError,
    overviewResult,
    setOverviewResult,
  } = useKeywordsSession()

  async function runOverview() {
    setOverviewLoading(true)
    setOverviewError(null)
    try {
      const data = await overviewKeyword({
        keyword: overviewQuery.trim(),
        locale: language,
      })
      setOverviewResult(data)
    } catch (err) {
      setOverviewResult(null)
      setOverviewError(
        err instanceof ApiError ? err.message : 'Something went wrong.',
      )
    } finally {
      setOverviewLoading(false)
    }
  }

  return (
    <>
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
            value={overviewQuery}
            onChange={(e) => setOverviewQuery(e.target.value)}
            required
            maxLength={120}
            placeholder="e.g. money transfer"
            className="w-full rounded-lg border border-surface-border bg-surface-elevated px-3 py-2 text-surface-foreground"
          />
        </label>
        <div className="text-sm sm:w-44">
          <span className="mb-1 block text-surface-subtle">Language</span>
          <KeywordLanguageSelect value={language} onChange={setLanguage} />
        </div>
        <button
          type="submit"
          disabled={overviewLoading || !overviewQuery.trim()}
          className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-hover disabled:opacity-50"
        >
          {overviewLoading ? 'Analyzing…' : 'Analyze'}
        </button>
      </form>

      {overviewError ? (
        <p className="mt-4 text-sm text-warning-strong" role="alert">
          {overviewError}
        </p>
      ) : null}

      {overviewResult ? (
        <div className="mt-8 space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-xl border border-surface-border bg-surface p-4">
              <p className="text-xs uppercase tracking-wide text-surface-subtle">
                Intent
              </p>
              <p className="mt-1 text-lg font-semibold capitalize">
                {signalText(overviewResult.signals, 'intent')}
              </p>
            </div>
            <div className="rounded-xl border border-surface-border bg-surface p-4">
              <p className="text-xs uppercase tracking-wide text-surface-subtle">
                Volume
              </p>
              <p className="mt-1 text-lg font-semibold">
                {signalNumber(overviewResult.signals, 'volume')}
              </p>
              <p className="mt-1 text-xs text-surface-subtle">
                {overviewResult.signals?.volume_estimated === false
                  ? 'Google Ads'
                  : '— (enable KEYWORD_ADS_ENABLED)'}
              </p>
            </div>
            <div className="rounded-xl border border-surface-border bg-surface p-4">
              <p className="text-xs uppercase tracking-wide text-surface-subtle">
                Est. demand
              </p>
              <p className="mt-1 text-lg font-semibold">
                {signalNumber(overviewResult.signals, 'estimated_demand_score')}
              </p>
            </div>
            <div className="rounded-xl border border-surface-border bg-surface p-4">
              <p className="text-xs uppercase tracking-wide text-surface-subtle">
                Est. difficulty
              </p>
              <p className="mt-1 text-lg font-semibold">
                {signalNumber(
                  overviewResult.signals,
                  'estimated_difficulty_score',
                )}
              </p>
              <p className="mt-1 text-xs text-surface-subtle">
                Basis: {signalText(overviewResult.signals, 'difficulty_basis')}
              </p>
            </div>
          </div>

          <section>
            <h2 className="text-lg font-semibold text-surface-foreground">
              Sample ideas
            </h2>
            <ul className="mt-3 divide-y divide-surface-border rounded-xl border border-surface-border bg-surface">
              {(overviewResult.sample_ideas ?? []).map((idea) => (
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
    </>
  )
}
