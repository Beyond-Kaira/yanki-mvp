import Button from '@/components/Button'
import Link from 'next/link'
import type { SeoProject, SiteAuditRunSummary } from '@/lib/contracts'

const STATUS_LABEL: Record<SiteAuditRunSummary['status'], string> = {
  queued: 'Queued',
  running: 'Auditing',
  done: 'Complete',
  failed: 'Failed',
}

const STATUS_TONE: Record<SiteAuditRunSummary['status'], string> = {
  queued: 'bg-surface-muted text-surface-subtle',
  running: 'bg-primary-soft text-primary-strong',
  done: 'bg-success-soft text-success-strong',
  failed: 'bg-danger-soft text-danger-strong',
}

const DATE_FORMATTER = new Intl.DateTimeFormat('en', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
})

function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Unknown' : DATE_FORMATTER.format(date)
}

/** Stroke weight and box match the Admin Panel's row icons, so the two tables
 *  do not read as different products. */
function TrashIcon() {
  return (
    <svg
      viewBox="0 0 20 20"
      aria-hidden="true"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-[18px] w-[18px]"
    >
      <path d="M3.5 5.5h13" />
      <path d="M8 5.5V4a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v1.5" />
      <path d="M5.75 5.5v10.25a1.25 1.25 0 0 0 1.25 1.25h6a1.25 1.25 0 0 0 1.25-1.25V5.5" />
      <path d="M8.5 9v4.5" />
      <path d="M11.5 9v4.5" />
    </svg>
  )
}

function AuditStatus({ audit }: { audit: SiteAuditRunSummary | null }) {
  if (!audit) {
    return <span className="text-sm text-surface-subtle">Not audited</span>
  }

  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${STATUS_TONE[audit.status]}`}
    >
      {STATUS_LABEL[audit.status]}
    </span>
  )
}

export default function SeoProjectList({
  projects,
  onCreateProject,
  onDeleteProject,
  deletingId,
}: {
  projects: SeoProject[]
  /** Omitted when the enqueue feature is off — the list stays a read-only view. */
  onCreateProject?: () => void
  /**
   * Removing a project is NOT tied to the enqueue feature flag: a project
   * created while crawling was dark still has to be removable, so this stays
   * available in both states. Omitted only for a caller with no delete path.
   */
  onDeleteProject?: (project: SeoProject) => void
  /** The row with a delete in flight, so its button can say so. */
  deletingId?: string | null
}) {
  return (
    <section
      aria-labelledby="seo-projects-heading"
      className="overflow-hidden rounded-xl border border-surface-border bg-surface shadow-sm"
    >
      <div className="flex flex-col gap-4 border-b border-surface-border px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div>
          <h2
            id="seo-projects-heading"
            className="text-xl font-semibold text-surface-foreground"
          >
            SEO projects
          </h2>
          <p className="mt-1 text-sm text-surface-subtle">
            Your domains and their latest Site Audit results.
          </p>
        </div>
        {onCreateProject ? (
          <Button onClick={onCreateProject} size="sm" className="self-start sm:self-auto">
            New SEO project
          </Button>
        ) : null}
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-[760px] w-full border-collapse text-left text-sm">
          <caption className="sr-only">
            SEO projects with their latest crawl status, health score, and issues
          </caption>
          <thead className="bg-surface-zebra text-xs font-medium uppercase tracking-wide text-surface-subtle">
            <tr>
              <th scope="col" className="px-5 py-3 sm:px-6">
                Project
              </th>
              <th scope="col" className="px-4 py-3">
                Last update
              </th>
              <th scope="col" className="px-4 py-3">
                Pages crawled
              </th>
              <th scope="col" className="px-4 py-3">
                Site health
              </th>
              <th scope="col" className="px-4 py-3">
                Issues
              </th>
              <th scope="col" className="px-5 py-3 sm:px-6">
                Status
              </th>
              {onDeleteProject ? (
                <th scope="col" className="px-4 py-3">
                  <span className="sr-only">Actions</span>
                </th>
              ) : null}
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-border">
            {projects.map((project) => {
              const audit = project.latest_audit
              const deleting = deletingId === project.id
              return (
                <tr key={project.id} className="align-top">
                  <th scope="row" className="px-5 py-4 font-normal sm:px-6">
                    <Link
                      href={`/site-audit/${project.id}`}
                      className="inline-flex min-h-[40px] items-center font-semibold text-primary hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                    >
                      {project.name}
                    </Link>
                    <span className="mt-0.5 block max-w-xs truncate text-surface-subtle">
                      {project.domain}
                    </span>
                  </th>
                  <td className="whitespace-nowrap px-4 py-4 text-surface-subtle">
                    <time dateTime={project.updated_at}>
                      {formatDate(project.updated_at)}
                    </time>
                  </td>
                  <td className="whitespace-nowrap px-4 py-4 text-surface-foreground">
                    {audit ? `${audit.pages_crawled} / ${audit.page_limit}` : '—'}
                  </td>
                  <td className="whitespace-nowrap px-4 py-4 font-medium text-surface-foreground">
                    {audit?.health_score == null ? '—' : `${audit.health_score}%`}
                  </td>
                  <td className="whitespace-nowrap px-4 py-4">
                    {audit ? (
                      <span className="flex flex-col gap-1">
                        <span className="text-danger-strong">
                          {audit.total_errors} errors
                        </span>
                        <span className="text-warning-strong">
                          {audit.total_warnings} warnings
                        </span>
                      </span>
                    ) : (
                      <span className="text-surface-subtle">—</span>
                    )}
                  </td>
                  <td className="px-5 py-4 sm:px-6">
                    <AuditStatus audit={audit} />
                  </td>
                  {onDeleteProject ? (
                    <td className="px-4 py-4 text-right">
                      <button
                        type="button"
                        disabled={deleting}
                        aria-label={`Delete ${project.name}`}
                        // An icon-only button that silently does nothing reads
                        // as broken, so the tooltip says which state it is in.
                        title={deleting ? 'Deleting…' : 'Delete project'}
                        onClick={() => onDeleteProject(project)}
                        className="inline-flex h-11 w-11 items-center justify-center rounded-md text-surface-subtle transition-colors hover:bg-danger-soft hover:text-danger-strong disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-surface-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger"
                      >
                        <TrashIcon />
                      </button>
                    </td>
                  ) : null}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
