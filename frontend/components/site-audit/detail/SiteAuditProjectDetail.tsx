'use client'

import { useParams } from 'next/navigation'
import { useCallback, useState } from 'react'
import Button from '@/components/Button'
import SiteAuditComparePanel from '@/components/site-audit/compare/SiteAuditComparePanel'
import SiteAuditSettingsDialog from '@/components/site-audit/dashboard/SiteAuditSettingsDialog'
import type { SiteAuditSettings } from '@/components/site-audit/dashboard/SiteAuditSettingsDialog'
import { ApiError, startSiteAudit } from '@/lib/api'
import SiteAuditIssuesPanel from '@/components/site-audit/issues/SiteAuditIssuesPanel'
import SiteAuditCrawledPagesPanel from '@/components/site-audit/pages/SiteAuditCrawledPagesPanel'
import SiteAuditOverview from '@/components/site-audit/overview/SiteAuditOverview'
import SiteAuditSchemaPanel from '@/components/site-audit/schema/SiteAuditSchemaPanel'
import { useSiteAuditProject } from '@/components/site-audit/hooks/useSiteAuditProject'
import SiteAuditProjectHeader from './SiteAuditProjectHeader'
import SiteAuditTabs from './SiteAuditTabs'
import type { SiteAuditTab } from './SiteAuditTabs'

export default function SiteAuditProjectDetail() {
  const { projectId } = useParams<{ projectId: string }>()
  const { state, retry } = useSiteAuditProject(projectId)
  const [tab, setTab] = useState<SiteAuditTab>('overview')
  const [configuring, setConfiguring] = useState(false)
  const [starting, setStarting] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)
  // The enqueue route answers 404 while the crawl is switched off in this
  // deployment (config.site_audit_enabled). Once seen, withdraw the button
  // rather than keep offering one that cannot work — the same choice the
  // dashboard makes for its create call-to-action.
  const [rerunUnavailable, setRerunUnavailable] = useState(false)

  // Memoised for ModalDialog's effect, and refusing while a request is in
  // flight so a stray Escape cannot abandon one — same shape as the dashboard's
  // `closeSettings`.
  const closeDialog = useCallback(() => {
    if (starting) return
    setConfiguring(false)
    setStartError(null)
  }, [starting])

  async function handleStart(settings: SiteAuditSettings) {
    setStarting(true)
    setStartError(null)
    try {
      await startSiteAudit(projectId, settings)
      setConfiguring(false)
      // Refetch rather than patch state in: the queued run is what the poller
      // needs to see to start following progress, and the server's copy of it
      // is the only one that is definitely right.
      retry()
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        setRerunUnavailable(true)
        setConfiguring(false)
        return
      }
      setStartError(
        error instanceof Error ? error.message : 'The Site Audit could not be started.',
      )
    } finally {
      setStarting(false)
    }
  }

  if (state.kind === 'loading') return <DetailLoading label="Loading Site Audit" />
  if (state.kind === 'error') {
    return (
      <DetailShell>
        <section
          role="alert"
          className="rounded-xl border border-danger bg-danger-soft p-8"
        >
          <h1 className="text-2xl font-semibold text-danger-strong">
            Site Audit could not be loaded
          </h1>
          <p className="mt-2 text-sm text-surface-foreground">{state.message}</p>
          <Button className="mt-5" onClick={retry}>
            Try again
          </Button>
        </section>
      </DetailShell>
    )
  }

  const { project, audit } = state
  const auditInFlight = ['queued', 'running'].includes(audit?.status ?? '')
  return (
    <DetailShell>
      <SiteAuditProjectHeader
        project={project}
        audit={audit}
        action={
          rerunUnavailable ? null : (
            <Button
              variant="secondary"
              onClick={() => {
                setStartError(null)
                setConfiguring(true)
              }}
              disabled={auditInFlight}
            >
              {auditInFlight
                ? 'Audit in progress'
                : audit
                  ? 'Run audit again'
                  : 'Run audit'}
            </Button>
          )
        }
      />

      {rerunUnavailable ? (
        <p
          role="status"
          className="mt-4 rounded-lg border border-surface-border bg-surface p-4 text-sm text-surface-subtle"
        >
          Starting a crawl is turned off in this deployment. This audit stays
          fully viewable, but a new run cannot be queued right now.
        </p>
      ) : null}

      {configuring ? (
        <SiteAuditSettingsDialog
          domain={project.domain}
          submitting={starting}
          submitError={startError}
          initialSettings={
            audit
              ? {
                  page_limit: audit.page_limit,
                  profile_id: audit.profile_id,
                  js_rendering: audit.js_rendering,
                }
              : undefined
          }
          onClose={closeDialog}
          onStart={handleStart}
        />
      ) : null}

      {!audit ? (
        <section className="mt-8 rounded-xl border border-surface-border bg-surface p-8 shadow-sm">
          <h2 className="text-xl font-semibold text-surface-foreground">
            No audit run yet
          </h2>
          <p className="mt-2 text-sm text-surface-subtle">
            This project does not have an audit result to display.
          </p>
        </section>
      ) : (
        <>
          <SiteAuditTabs activeTab={tab} onChange={setTab} />
          <div
            role="tabpanel"
            id={`site-audit-panel-${tab}`}
            aria-labelledby={`site-audit-tab-${tab}`}
            className="pt-5"
          >
            {tab === 'overview' ? (
              <SiteAuditOverview
                audit={audit}
                project={project}
                onViewAllIssues={() => setTab('issues')}
              />
            ) : null}
            {tab === 'issues' ? <SiteAuditIssuesPanel pages={audit.pages} /> : null}
            {tab === 'pages' ? (
              <SiteAuditCrawledPagesPanel pages={audit.pages} />
            ) : null}
            {tab === 'schema' ? <SiteAuditSchemaPanel pages={audit.pages} /> : null}
            {tab === 'compare' ? (
              <SiteAuditComparePanel
                projectId={projectId}
                project={project}
                loadedAudit={audit}
              />
            ) : null}
          </div>
        </>
      )}
    </DetailShell>
  )
}

function DetailShell({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto max-w-6xl px-4 pb-7 pt-4 sm:px-8 sm:pb-8 sm:pt-5">
      {children}
    </main>
  )
}

function DetailLoading({ label }: { label: string }) {
  return (
    <DetailShell>
      <p
        role="status"
        className="rounded-xl border border-surface-border bg-surface p-8 text-sm text-surface-subtle"
      >
        {label}…
      </p>
    </DetailShell>
  )
}
