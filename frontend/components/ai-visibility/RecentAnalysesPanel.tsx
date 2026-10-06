'use client'

import Link from 'next/link'
import type { AnalysisEnvelope } from '@/lib/contracts'
import { analysisStatusLabel } from '@/lib/guided-analysis'
import AnalysisProgressCard from '@/components/ai-visibility/AnalysisProgressCard'
import { useAnalysesList } from '@/components/ai-visibility/useAnalysesList'
import { useCollapseScrollGuard } from '@/components/ai-visibility/useCollapseScrollGuard'

const RECENT_LIMIT = 5

const STATUS_TONE: Record<string, string> = {
  done: 'bg-success-soft text-success-strong',
  running: 'bg-primary-soft text-primary-strong',
  queued: 'bg-surface-muted text-surface-subtle',
  awaiting_review: 'bg-warning-soft text-warning-strong',
  failed: 'bg-danger-soft text-danger-strong',
}

function readableTarget(url: string): string {
  return url.replace(/^https?:\/\//, '').replace(/\/$/, '')
}

function formatMoment(value: string): string {
  return new Date(value).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/**
 * The caller's own recent runs on AI Visibility — a way back without leaving
 * the product area. Full history lives on `/analyses`.
 */
export default function RecentAnalysesPanel({
  className = '',
  activeAnalysis = null,
  overviewPath = '/ai-visibility',
}: {
  className?: string
  activeAnalysis?: AnalysisEnvelope | null
  overviewPath?: '/ai-visibility' | '/search-visibility'
}) {
  const { page, loading, error, announcement } = useAnalysesList({ limit: RECENT_LIMIT })
  const rows = page?.analyses ?? []
  // Direct links may point at a run outside the five most recent entries.
  // Keep that run visible while the list loads without duplicating its row.
  const visibleRows = activeAnalysis && !rows.some((row) => row.id === activeAnalysis.id)
    ? [activeAnalysis, ...rows] : rows
  const visible = loading || Boolean(error) || visibleRows.length > 0
  const { sectionRef, contentRef, preserveScroll } = useCollapseScrollGuard(visible)

  if (!visible) {
    return null
  }

  return (
    <section ref={sectionRef} className={`[overflow-anchor:none] ${className}`} aria-labelledby="recent-analyses-heading">
      <div ref={contentRef}>
        <p aria-live="polite" className="sr-only">{announcement}</p>
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <h2
            id="recent-analyses-heading"
            className="text-lg font-semibold tracking-tight"
          >
            Your analyses
          </h2>
          <Link
            href="/analyses"
            className="text-sm font-medium text-primary-strong underline underline-offset-2"
          >
            View all
          </Link>
        </div>
        {loading && visibleRows.length === 0 ? <p className="text-sm text-surface-subtle">Loading…</p> : null}
        {error ? <p role="alert" className="mb-3 text-sm text-danger-strong">{error}</p> : null}
        <ul className="space-y-3">
          {visibleRows.map((row) => (
            <li key={row.id}>
              {row.status === 'running' || row.status === 'queued' || row.status === 'awaiting_review' || row.status === 'failed' ? (
                <AnalysisProgressCard analysis={row} onCollapse={preserveScroll} />
              ) : (
              <Link
                href={`${overviewPath}?analysis=${encodeURIComponent(row.id)}`}
                className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-surface-border bg-surface px-4 py-3 text-sm hover:bg-surface-muted/60"
              >
                <span className="w-full min-w-0 break-all font-medium text-primary-strong sm:w-auto sm:flex-1">
                  {readableTarget(row.url)}
                </span>
                <span className="flex w-full min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-surface-subtle sm:w-auto">
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                      STATUS_TONE[row.status] ?? 'bg-surface-muted'
                    }`}
                  >
                    {analysisStatusLabel(row.status)}
                  </span>
                  <span className="tabular-nums">
                    {row.geo_score == null ? '—' : row.geo_score.toFixed(1)}
                  </span>
                  <span>{formatMoment(row.created_at)}</span>
                </span>
              </Link>
              )}
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}
