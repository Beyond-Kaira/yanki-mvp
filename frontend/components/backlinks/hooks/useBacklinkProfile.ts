import { useEffect, useState } from 'react'
import { ApiError, getBacklinkSummary, getSeoProject } from '@/lib/api'
import type { BacklinkSummary, SeoProjectDetail } from '@/lib/contracts'

export type BacklinkProfileState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  /** The module is switched off for this deployment — not an error. */
  | { kind: 'disabled'; project: SeoProjectDetail }
  | { kind: 'loaded'; project: SeoProjectDetail; summary: BacklinkSummary }

/** Load one project's backlink profile, telling "off" apart from "missing".
 *
 * The backend answers 404 for BOTH a disabled module and an unknown project,
 * and that is deliberate: a kill switch that says "this feature exists but is
 * disabled" has already told an anonymous prober the thing it was hiding.
 *
 * The client can still resolve it without weakening that, by asking a question
 * the backlink routes are not the authority on — does the SEO project itself
 * load? If the project is fine and only the backlink call 404s, the module is
 * off. If the project itself 404s, it genuinely is not there.
 *
 * Deliberately NOT done by matching on the error's `detail` string: that would
 * couple the UI to prose, and the prose is the one part of a 404 anybody may
 * reword at any time.
 */
export function useBacklinkProfile(projectId: string) {
  const [state, setState] = useState<BacklinkProfileState>({ kind: 'loading' })
  const [requestVersion, setRequestVersion] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false
    setState({ kind: 'loading' })

    async function load() {
      let project: SeoProjectDetail
      try {
        project = await getSeoProject(projectId, controller.signal)
      } catch (error) {
        if (cancelled || (error instanceof Error && error.name === 'AbortError')) {
          return
        }
        setState({
          kind: 'error',
          message:
            error instanceof Error
              ? error.message
              : 'This project could not be loaded.',
        })
        return
      }

      try {
        const summary = await getBacklinkSummary(projectId, controller.signal)
        if (cancelled) return
        setState({ kind: 'loaded', project, summary })
      } catch (error) {
        if (cancelled || (error instanceof Error && error.name === 'AbortError')) {
          return
        }
        if (error instanceof ApiError && error.status === 404) {
          setState({ kind: 'disabled', project })
          return
        }
        setState({
          kind: 'error',
          message:
            error instanceof Error
              ? error.message
              : 'The backlink profile could not be loaded.',
        })
      }
    }

    void load()
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [projectId, requestVersion])

  return {
    state,
    reload: () => setRequestVersion((version) => version + 1),
  }
}
