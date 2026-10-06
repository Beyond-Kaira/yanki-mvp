'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, getAnalysis, listAnalyses, type AnalysisHistoryQuery } from '@/lib/api'
import type { AnalysisList, AnalysisSummary } from '@/lib/contracts'
import { notifyAnalysisQuotaChanged, subscribeAnalysisQuotaChanged } from '@/lib/analysis-quota-events'
import { useAnalysisSession, type TrackedAnalysis } from '@/components/AnalysisSessionProvider'

export const ANALYSES_POLL_MS = 2000
const EMPTY_TRACKED: readonly TrackedAnalysis[] = []
const isLive = (row: AnalysisSummary) => row.status === 'running' || row.status === 'queued'

/** Keep live history rows current without replacing the page during refresh. */
export function useAnalysesList({ status, limit, offset }: AnalysisHistoryQuery) {
  const [page, setPage] = useState<AnalysisList | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [announcement, setAnnouncement] = useState('')
  const requestRef = useRef<AbortController | null>(null)
  const previousStatuses = useRef(new Map<string, string>())
  const pageRef = useRef<AnalysisList | null>(null)
  const unlistedRows = useRef(new Map<string, AnalysisSummary>())
  const { trackedAnalyses = EMPTY_TRACKED, settleAnalyses, sessionScope } = useAnalysisSession()
  const sessionRef = useRef({ trackedAnalyses, settleAnalyses })
  const pageScope = useRef(sessionScope)
  sessionRef.current = { trackedAnalyses, settleAnalyses }
  const includeTracked = !offset && (!status || status === 'queued' || status === 'running')

  const reload = useCallback(async () => {
    requestRef.current?.abort()
    const request = new AbortController()
    requestRef.current = request
    setLoading(true)
    try {
      // A missing list row is not evidence that a submitted job stopped.
      // Resolve jobs by ID and retain their last known state on transient errors.
      let next: AnalysisList
      let refreshError: string | null = null
      try {
        next = await listAnalyses({ status, limit, offset }, request.signal)
      } catch (cause) {
        if (request.signal.aborted) return
        refreshError = cause instanceof Error ? cause.message : "We couldn't load your analyses."
        next = pageRef.current ?? { analyses: [], total: 0, limit: limit ?? 20, offset: offset ?? 0, user_analyses_used: 0, user_analyses_limit: 5 }
      }
      if (request.signal.aborted) return
      if (!refreshError) for (const row of next.analyses) unlistedRows.current.delete(row.id)
      const known = new Map([
        ...unlistedRows.current,
        ...(pageRef.current?.analyses ?? []).filter(isLive).map(row => [row.id, row] as const),
      ])
      const tracked = includeTracked ? sessionRef.current.trackedAnalyses : EMPTY_TRACKED
      for (const run of tracked) {
        if (run.initial && !known.has(run.id)) known.set(run.id, run.initial)
      }
      const missingIds = [...new Set([...known.keys(), ...tracked.map(run => run.id)])]
        .filter(id => refreshError || !next.analyses.some(row => row.id === id))
      const reads = await Promise.allSettled(missingIds.map(id => getAnalysis(id, request.signal)))
      if (request.signal.aborted) return
      const rows = new Map(next.analyses.map(row => [row.id, row]))
      const settledIds: string[] = []
      reads.forEach((read, index) => {
        const id = missingIds[index]
        if (read.status === 'fulfilled') {
          const row = read.value
          unlistedRows.current.set(id, row)
          if (!status || row.status === status) rows.set(id, row)
          else rows.delete(id)
          if (!isLive(row)) settledIds.push(id)
        } else if (read.reason instanceof ApiError && [403, 404, 422].includes(read.reason.status)) {
          rows.delete(id)
          unlistedRows.current.delete(id)
          settledIds.push(id)
          refreshError ??= "We couldn't find that analysis. Refresh the page or start a new analysis."
        } else {
          const previous = known.get(id)
          if (previous && (!status || previous.status === status)) rows.set(id, previous)
          refreshError ??= "We couldn't refresh analysis progress. Retrying automatically."
        }
      })
      // Fresh rows from the list also settle submitted jobs.
      for (const row of rows.values()) if (!isLive(row)) settledIds.push(row.id)
      next = { ...next, analyses: [...rows.values()].sort((a, b) => b.created_at.localeCompare(a.created_at) || b.id.localeCompare(a.id)) }
      let freedSlot = false
      const outcomes = next.analyses.flatMap((row) => {
        const previous = previousStatuses.current.get(row.id) ?? (tracked.some(run => run.id === row.id) ? 'queued' : undefined)
        if (previous !== 'running' && previous !== 'queued') return []
        const target = row.url.replace(/^https?:\/\//, '').replace(/\/$/, '')
        if (row.status === 'done') return [`Analysis for ${target} complete. Your results are ready.`]
        if (row.status === 'awaiting_review') return [`Analysis for ${target} is ready for your review.`]
        if (row.status === 'failed') {
          freedSlot = true
          return [`Analysis for ${target} failed. ${row.error ?? ''}`]
        }
        return []
      })
      if (outcomes.length) setAnnouncement(outcomes.join(' '))
      previousStatuses.current = new Map(next.analyses.map((row) => [row.id, row.status]))
      pageRef.current = next
      setPage(next)
      setError(refreshError)
      sessionRef.current.settleAnalyses?.(settledIds)
      if (freedSlot) notifyAnalysisQuotaChanged()
    } catch (cause) {
      if (request.signal.aborted) return
      setError(cause instanceof Error ? cause.message : "We couldn't load your analyses.")
    } finally {
      if (!request.signal.aborted) {
        requestRef.current = null
        setLoading(false)
      }
    }
  }, [status, limit, offset, includeTracked])

  useEffect(() => {
    pageRef.current = null
    unlistedRows.current.clear()
    pageScope.current = sessionScope
    previousStatuses.current.clear()
    setPage(null)
    setAnnouncement('')
    void reload()
    const unsubscribe = subscribeAnalysisQuotaChanged(() => void reload())
    const onFocus = () => void reload()
    window.addEventListener('focus', onFocus)
    return () => {
      unsubscribe()
      window.removeEventListener('focus', onFocus)
      requestRef.current?.abort()
    }
  }, [reload, sessionScope])

  const trackedKey = includeTracked ? trackedAnalyses.map(run => run.id).join(',') : ''
  useEffect(() => {
    // Starts (including restored IDs) trigger a read. Settling a job does not
    // replace its final row with an older list snapshot.
    if (trackedKey && trackedKey.split(',').some(id => !pageRef.current?.analyses.some(row => row.id === id))) void reload()
  }, [trackedKey, reload])

  const hasLiveRuns = (page?.analyses.some(isLive) ?? false) || Boolean(trackedKey)
  useEffect(() => {
    if (!hasLiveRuns) return
    const timer = setInterval(() => {
      // Skip a tick while the previous request is in flight; a slow response
      // must still be allowed to finish. Explicit reloads supersede old reads.
      if (!requestRef.current) void reload()
    }, ANALYSES_POLL_MS)
    return () => clearInterval(timer)
  }, [hasLiveRuns, reload])

  const scopedPage = pageScope.current === sessionScope ? page : null
  const seeds = includeTracked ? trackedAnalyses.flatMap(run => run.initial && (!status || run.initial.status === status) && !scopedPage?.analyses.some(row => row.id === run.id) ? [run.initial] : []) : []
  const visiblePage = seeds.length ? {
    ...(scopedPage ?? { total: 0, limit: limit ?? 20, offset: offset ?? 0, user_analyses_used: 0, user_analyses_limit: 5 }),
    analyses: [...seeds, ...(scopedPage?.analyses ?? [])],
  } : scopedPage
  return { page: visiblePage, loading, error, reload, announcement }
}
