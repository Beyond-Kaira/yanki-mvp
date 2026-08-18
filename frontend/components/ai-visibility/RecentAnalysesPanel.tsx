'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { ApiError, listAnalyses } from '@/lib/api'
import type { AnalysisSummary } from '@/lib/contracts'

const RECENT_LIMIT = 5

const STATUS_TONE: Record<string, string> = {
  done: 'bg-success-soft text-success-strong',
  running: 'bg-primary-soft text-primary-strong',
  queued: 'bg-surface-muted text-surface-subtle',
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
}: {
  className?: string
}) {
  const [rows, setRows] = useState<AnalysisSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback((signal?: AbortSignal) => {
    setLoading(true)
    setError(null)
    listAnalyses({ limit: RECENT_LIMIT }, signal)
      .then((page) => {
        setRows(page.analyses)
        setLoading(false)
      })
      .catch((cause: unknown) => {
        if (cause instanceof Error && cause.name === 'AbortError') return
        setError(
          cause instanceof ApiError
            ? cause.message
            : "We couldn't load your recent analyses.",
        )
        setLoading(false)
      })
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal)
    return () => controller.abort()
  }, [load])

  if (loading) {
    return (
      <section className={className} aria-labelledby="recent-analyses-heading">
        <h2
          id="recent-analyses-heading"
          className="text-lg font-semibold tracking-tight"
        >
          Your analyses
        </h2>
        <p className="mt-2 text-sm text-surface-subtle">Loading…</p>
      </section>
    )
  }

  if (error) {
    return (
      <section className={className} aria-labelledby="recent-analyses-heading">
        <h2
          id="recent-analyses-heading"
          className="text-lg font-semibold tracking-tight"
        >
          Your analyses
        </h2>
        <p role="alert" className="mt-2 text-sm text-danger-strong">
          {error}
        </p>
      </section>
    )
  }

  if (rows.length === 0) {
    return null
  }

  return (
    <section className={className} aria-labelledby="recent-analyses-heading">
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
      <ul className="divide-y divide-surface-border rounded-2xl border border-surface-border bg-surface">
        {rows.map((row) => (
          <li key={row.id}>
            <Link
              href={`/ai-visibility?analysis=${row.id}`}
              className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 text-sm hover:bg-surface-muted/60"
            >
              <span className="min-w-0 flex-1 font-medium text-primary-strong">
                {readableTarget(row.url)}
              </span>
              <span className="flex items-center gap-3 text-surface-subtle">
                <span
                  className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                    STATUS_TONE[row.status] ?? 'bg-surface-muted'
                  }`}
                >
                  {row.status}
                </span>
                <span className="tabular-nums">
                  {row.geo_score == null ? '—' : row.geo_score.toFixed(1)}
                </span>
                <span>{formatMoment(row.created_at)}</span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}
