import { useEffect, useState } from 'react'
import { getSeoProject, getSiteAudit } from '@/lib/api'
import type { SeoProjectDetail, SiteAuditDetail } from '@/lib/contracts'

const POLL_MS = 2500

export type SiteAuditProjectState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'loaded'; project: SeoProjectDetail; audit: SiteAuditDetail | null }

export function useSiteAuditProject(projectId: string, enabled: boolean) {
  const [state, setState] = useState<SiteAuditProjectState>({ kind: 'loading' })
  const [requestVersion, setRequestVersion] = useState(0)

  useEffect(() => {
    if (!enabled) return
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | null = null
    let cancelled = false
    setState({ kind: 'loading' })

    async function load() {
      try {
        const project = await getSeoProject(projectId, controller.signal)
        const audit = project.latest_audit
          ? await getSiteAudit(projectId, project.latest_audit.id, controller.signal)
          : null
        if (cancelled) return
        setState({ kind: 'loaded', project, audit })
        if (audit && ['queued', 'running'].includes(audit.status)) {
          timer = setTimeout(load, POLL_MS)
        }
      } catch (error) {
        if (cancelled || (error instanceof Error && error.name === 'AbortError')) {
          return
        }
        setState({
          kind: 'error',
          message:
            error instanceof Error
              ? error.message
              : 'The Site Audit project could not be loaded.',
        })
      }
    }

    void load()
    return () => {
      cancelled = true
      controller.abort()
      if (timer) clearTimeout(timer)
    }
  }, [enabled, projectId, requestVersion])

  return {
    state,
    retry: () => setRequestVersion((version) => version + 1),
  }
}
