'use client'

import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'
import SeoProjectList from './SeoProjectList'
import SiteAuditProjectStart from './SiteAuditProjectStart'
import SiteAuditSettingsDialog from './SiteAuditSettingsDialog'
import type { SiteAuditSettings } from './SiteAuditSettingsDialog'
import { ApiError, createSeoProject, listSeoProjects } from '@/lib/api'
import type { SeoProject } from '@/lib/contracts'

type ProjectState =
  | { kind: 'loading' }
  | { kind: 'loaded'; projects: SeoProject[] }
  | { kind: 'error'; message: string }

export default function SiteAuditDashboard() {
  const [requestVersion, setRequestVersion] = useState(0)
  const [projectState, setProjectState] = useState<ProjectState>({
    kind: 'loading',
  })
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [pendingDomain, setPendingDomain] = useState<string | null>(null)
  const [creatingProject, setCreatingProject] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  // Site Audit's crawl is gated off while no worker drains the queue
  // (config.site_audit_enabled). Project creation stays open — the project is
  // the shared entity Backlinks hangs off — so a create no longer 404s; instead
  // it succeeds with `latest_audit: null`, meaning no crawl was queued. That
  // absent audit is the honest signal the feature is dark. Once seen, we replace
  // the start CTA with a notice rather than imply a crawl is running. (We still
  // treat a 404 as the same signal for older deployments / the rerun route.)
  const [featureDisabled, setFeatureDisabled] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    setProjectState({ kind: 'loading' })

    void listSeoProjects(controller.signal).then(
      (projects) => {
        if (!controller.signal.aborted) {
          setProjectState({ kind: 'loaded', projects })
        }
      },
      (error: unknown) => {
        if (!controller.signal.aborted) {
          setProjectState({
            kind: 'error',
            message:
              error instanceof Error
                ? error.message
                : 'Site Audit projects could not be loaded.',
          })
        }
      },
    )

    return () => controller.abort()
  }, [requestVersion])

  const hasActiveAudit =
    projectState.kind === 'loaded' &&
    projectState.projects.some((project) =>
      ['queued', 'running'].includes(project.latest_audit?.status ?? ''),
    )

  useEffect(() => {
    if (!hasActiveAudit) return

    let cancelled = false
    const timer = window.setInterval(() => {
      void listSeoProjects().then(
        (projects) => {
          if (!cancelled) setProjectState({ kind: 'loaded', projects })
        },
        () => {
          // Preserve the last useful list if one background refresh fails.
          // The initial request and explicit retry still surface persistent errors.
        },
      )
    }, 2500)

    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [hasActiveAudit])

  const closeSettings = useCallback(() => {
    if (creatingProject) return
    setPendingDomain(null)
    setCreateError(null)
  }, [creatingProject])

  async function startAudit(settings: SiteAuditSettings) {
    if (!pendingDomain) return

    setCreatingProject(true)
    setCreateError(null)
    try {
      const project = await createSeoProject({
        domain: pendingDomain,
        name: null,
        ...settings,
      })
      // The project exists either way — keep it listed and viewable.
      setProjectState((current) => ({
        kind: 'loaded',
        projects:
          current.kind === 'loaded'
            ? [project, ...current.projects.filter((item) => item.id !== project.id)]
            : [project],
      }))
      setPendingDomain(null)
      setShowCreateForm(false)
      if (!project.latest_audit) {
        // Created, but no crawl was queued: Site Audit is off in this
        // deployment. Say so honestly instead of showing a project that would
        // otherwise look like it is about to be audited.
        setFeatureDisabled(true)
      }
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        // Feature is off in this deployment: stop offering the CTA and say so.
        setFeatureDisabled(true)
        setPendingDomain(null)
        setShowCreateForm(false)
        setCreateError(null)
        return
      }
      setCreateError(
        error instanceof Error ? error.message : 'The Site Audit could not be started.',
      )
    } finally {
      setCreatingProject(false)
    }
  }

  return (
    <main className="mx-auto max-w-4xl px-4 py-10 sm:px-8 sm:py-12">
      <header className="mb-7 max-w-3xl">
        <p className="font-mono text-xs font-medium uppercase tracking-[0.18em] text-primary-strong">
          Technical SEO
        </p>
        <h1 className="mt-2 text-4xl font-semibold tracking-tight text-surface-foreground sm:text-5xl">
          Site Audit
        </h1>
        <p className="mt-2 max-w-2xl text-base leading-relaxed text-surface-subtle">
          Track crawl progress, site health, and technical issues for every domain in
          your workspace.
        </p>
      </header>

      <ProjectContent
        state={projectState}
        featureDisabled={featureDisabled}
        onRetry={() => setRequestVersion((version) => version + 1)}
        showCreateForm={showCreateForm}
        onShowCreateForm={() => setShowCreateForm(true)}
        onConfigure={(domain) => {
          setCreateError(null)
          setPendingDomain(domain)
        }}
      />

      {pendingDomain && !featureDisabled ? (
        <SiteAuditSettingsDialog
          domain={pendingDomain}
          submitting={creatingProject}
          submitError={createError}
          onClose={closeSettings}
          onStart={startAudit}
        />
      ) : null}
    </main>
  )
}

function ProjectContent({
  state,
  featureDisabled,
  onRetry,
  showCreateForm,
  onShowCreateForm,
  onConfigure,
}: {
  state: ProjectState
  featureDisabled: boolean
  onRetry: () => void
  showCreateForm: boolean
  onShowCreateForm: () => void
  onConfigure: (domain: string) => void
}) {
  if (state.kind === 'loading') {
    return (
      <section
        role="status"
        aria-live="polite"
        className="rounded-xl border border-surface-border bg-surface p-8 shadow-sm"
      >
        <div className="space-y-3" aria-hidden="true">
          <div className="h-5 w-40 animate-pulse rounded bg-primary-soft motion-reduce:animate-none" />
          <div className="h-4 w-full max-w-xl animate-pulse rounded bg-surface-border motion-reduce:animate-none" />
          <div className="h-16 w-full animate-pulse rounded bg-surface-muted motion-reduce:animate-none" />
        </div>
        <span className="sr-only">Loading SEO projects</span>
      </section>
    )
  }

  if (state.kind === 'error') {
    return (
      <section
        role="alert"
        className="rounded-xl border border-danger bg-danger-soft p-8"
      >
        <h2 className="text-xl font-semibold text-danger-strong">
          Projects could not be loaded
        </h2>
        <p className="mt-2 max-w-xl text-sm text-surface-foreground">
          {state.message}
        </p>
        <button
          type="button"
          onClick={onRetry}
          className="mt-5 inline-flex min-h-[44px] items-center rounded-md border border-danger-strong px-4 text-sm font-medium text-danger-strong hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger-strong focus-visible:ring-offset-2"
        >
          Try again
        </button>
      </section>
    )
  }

  // Feature off in this deployment. Existing projects stay fully viewable (their
  // reads are not gated); only the enqueue call-to-action is withdrawn, with an
  // honest explanation in its place.
  if (featureDisabled) {
    if (state.projects.length === 0) {
      return <SiteAuditUnavailable />
    }
    return (
      <div className="space-y-6">
        <SiteAuditUnavailable />
        <SeoProjectList projects={state.projects} />
      </div>
    )
  }

  if (state.projects.length === 0) {
    return <SiteAuditProjectStart onContinue={onConfigure} />
  }

  return (
    <div className="space-y-6">
      {showCreateForm ? (
        <SiteAuditProjectStart onContinue={onConfigure} compact />
      ) : null}
      <p className="sr-only" aria-live="polite">
        {hasRunningProject(state.projects)
          ? 'A Site Audit is in progress. Project status updates automatically.'
          : ''}
      </p>
      <SeoProjectList projects={state.projects} onCreateProject={onShowCreateForm} />
    </div>
  )
}

function SiteAuditUnavailable() {
  return (
    <section
      role="status"
      className="rounded-xl border border-surface-border bg-surface p-8 shadow-sm"
    >
      <h2 className="text-xl font-semibold text-surface-foreground">
        Site Audit isn&rsquo;t available yet
      </h2>
      <p className="mt-2 max-w-2xl text-sm leading-relaxed text-surface-subtle">
        Starting a crawl is turned off in this deployment. Your projects are
        saved and stay fully viewable below, but no audit has been started for
        them &mdash; we&rsquo;re not showing a button that would only leave one
        stuck. Please check back once Site Audit is switched on.
      </p>
    </section>
  )
}

function hasRunningProject(projects: SeoProject[]): boolean {
  return projects.some((project) =>
    ['queued', 'running'].includes(project.latest_audit?.status ?? ''),
  )
}
