'use client'

import { useParams } from 'next/navigation'
import { useState } from 'react'
import Button from '@/components/Button'
import BacklinkInventoryPanel from '@/components/backlinks/inventory/BacklinkInventoryPanel'
import ReferringDomainsPanel from '@/components/backlinks/domains/ReferringDomainsPanel'
import LinkEventsPanel from '@/components/backlinks/events/LinkEventsPanel'
import OpportunitiesPanel from '@/components/backlinks/opportunities/OpportunitiesPanel'
import BacklinkOverview from '@/components/backlinks/overview/BacklinkOverview'
import BacklinksDisabledNotice from '@/components/backlinks/shared/BacklinksDisabledNotice'
import PageContainer from '@/components/shell/PageContainer'
import { useBacklinkProfile } from '@/components/backlinks/hooks/useBacklinkProfile'
import BacklinkProfileHeader from './BacklinkProfileHeader'
import BacklinkTabs from './BacklinkTabs'
import type { BacklinkTab } from './BacklinkTabs'

export default function BacklinkProfileDetail() {
  const { projectId } = useParams<{ projectId: string }>()
  const { state, reload } = useBacklinkProfile(projectId)
  const [tab, setTab] = useState<BacklinkTab>('overview')

  if (state.kind === 'loading') return <DetailLoading label="Loading backlinks" />

  if (state.kind === 'error') {
    return (
      <DetailShell>
        <section
          role="alert"
          className="rounded-xl border border-danger bg-danger-soft p-8"
        >
          <h1 className="text-2xl font-semibold text-danger-strong">
            Backlinks could not be loaded
          </h1>
          <p className="mt-2 text-sm text-surface-foreground">{state.message}</p>
          <Button className="mt-5" onClick={reload}>
            Try again
          </Button>
        </section>
      </DetailShell>
    )
  }

  if (state.kind === 'disabled') {
    return (
      <DetailShell>
        <p className="text-sm font-medium text-surface-subtle">Backlinks</p>
        <h1 className="mt-1 text-3xl font-semibold text-surface-foreground">
          {state.project.name}
        </h1>
        <p className="mt-1 mb-6 text-sm text-surface-subtle">
          {state.project.domain}
        </p>
        <BacklinksDisabledNotice domain={state.project.domain} />
      </DetailShell>
    )
  }

  const { project, summary } = state
  return (
    <DetailShell>
      <BacklinkProfileHeader
        project={project}
        summary={summary}
        onRefreshed={reload}
      />
      <BacklinkTabs activeTab={tab} onChange={setTab} />
      <div
        role="tabpanel"
        id={`backlinks-panel-${tab}`}
        aria-labelledby={`backlinks-tab-${tab}`}
        className="pt-5"
      >
        {tab === 'overview' ? (
          <BacklinkOverview
            summary={summary}
            onViewDomains={() => setTab('domains')}
          />
        ) : null}
        {tab === 'backlinks' ? (
          <BacklinkInventoryPanel projectId={project.id} />
        ) : null}
        {tab === 'domains' ? <ReferringDomainsPanel projectId={project.id} /> : null}
        {tab === 'events' ? <LinkEventsPanel projectId={project.id} /> : null}
        {tab === 'opportunities' ? (
          <OpportunitiesPanel projectId={project.id} />
        ) : null}
      </div>
    </DetailShell>
  )
}

function DetailShell({ children }: { children: React.ReactNode }) {
  return (
    <PageContainer>
      {children}
    </PageContainer>
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
