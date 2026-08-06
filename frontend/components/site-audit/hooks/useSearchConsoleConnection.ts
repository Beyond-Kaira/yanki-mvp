import { useCallback, useEffect, useState } from 'react'
import { getSearchConsolePerformance, listSearchConsoleConnections } from '@/lib/api'
import type { SearchConsoleConnections, SearchConsolePerformance } from '@/lib/contracts'

/**
 * Connection standing, and the performance summary that depends on it.
 *
 * Same shape as `useSiteAuditProject`: an `AbortController` per run, a
 * `requestVersion` counter for retry and post-mutation reload, and a `cancelled`
 * flag so a resolved-but-stale response cannot overwrite fresher state.
 *
 * The two loads are kept as **separate** pieces of state on purpose. Connections
 * are local rows; performance is a live call to Google that can rate-limit, time
 * out, or find a property whose access was revoked. Folding them into one union
 * would mean a Google outage blanks the card that is supposed to explain the
 * outage — so a failed performance fetch degrades to a message inside a card
 * that still renders the account and the property.
 *
 * Performance is deliberately **not** polled. It costs a token refresh and three
 * Search Console queries per call, so it runs once per load and once per change.
 */

export type SearchConsoleState =
  | { kind: 'loading' }
  // The module is switched off. The backend 404s the whole surface while
  // GSC_ENABLED is false — deliberately, so a disabled feature is
  // indistinguishable from one that does not exist. Honouring that means
  // rendering nothing, not a red box on every Site Audit page announcing the
  // feature we just chose to hide.
  | { kind: 'unavailable' }
  | { kind: 'error'; message: string }
  | { kind: 'loaded'; connections: SearchConsoleConnections }

export type PerformanceState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'loaded'; performance: SearchConsolePerformance }

export function useSearchConsoleConnection(projectId: string, enabled: boolean) {
  const [state, setState] = useState<SearchConsoleState>({ kind: 'loading' })
  const [performance, setPerformance] = useState<PerformanceState>({ kind: 'idle' })
  const [requestVersion, setRequestVersion] = useState(0)

  useEffect(() => {
    if (!enabled) return
    const controller = new AbortController()
    let cancelled = false
    setState({ kind: 'loading' })

    async function load() {
      let connections: SearchConsoleConnections
      try {
        connections = await listSearchConsoleConnections(projectId, controller.signal)
      } catch (error) {
        if (cancelled || (error instanceof Error && error.name === 'AbortError')) return
        // Read off the error rather than `instanceof ApiError` so this still
        // works where tests replace the whole api module.
        if ((error as { status?: number })?.status === 404) {
          setState({ kind: 'unavailable' })
          return
        }
        setState({
          kind: 'error',
          message:
            error instanceof Error
              ? error.message
              : 'Google connections could not be loaded.',
        })
        return
      }

      if (cancelled) return
      setState({ kind: 'loaded', connections })

      // Only a connected project has anything to fetch. Asking otherwise would
      // spend a Google call to be told what this response already said.
      if (connections.project_status !== 'connected') {
        setPerformance({ kind: 'idle' })
        return
      }

      setPerformance({ kind: 'loading' })
      try {
        const result = await getSearchConsolePerformance(projectId, controller.signal)
        if (cancelled) return
        setPerformance({ kind: 'loaded', performance: result })
      } catch (error) {
        if (cancelled || (error instanceof Error && error.name === 'AbortError')) return
        setPerformance({
          kind: 'error',
          message:
            error instanceof Error
              ? error.message
              : 'Search Console performance could not be loaded.',
        })
      }
    }

    void load()
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [enabled, projectId, requestVersion])

  const reload = useCallback(() => {
    setRequestVersion((version) => version + 1)
  }, [])

  return { state, performance, reload }
}
