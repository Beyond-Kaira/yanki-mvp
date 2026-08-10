'use client'

import { useParams } from 'next/navigation'
import { useState } from 'react'
import Button from '@/components/Button'
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
  return (
    <DetailShell>
      <SiteAuditProjectHeader project={project} audit={audit} />

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
