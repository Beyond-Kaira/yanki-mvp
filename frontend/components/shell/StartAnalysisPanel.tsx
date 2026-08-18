'use client'

import Link from 'next/link'
import UrlForm from '@/components/UrlForm'
import AnalysisQuotaChip from '@/components/ai-visibility/AnalysisQuotaChip'
import { useUserAnalysisQuota } from '@/components/ai-visibility/useUserAnalysisQuota'

/** Empty-state for product shell: start a domain analysis (not sample metrics). */
export default function StartAnalysisPanel({
  title = 'Run an analysis',
  description = 'Enter your company domain. We crawl the site, ask AI engines about your brand, and build your GEO score.',
}: {
  title?: string
  description?: string
}) {
  const { quota, atLimit, loading: quotaLoading } = useUserAnalysisQuota()

  return (
    <div className="mx-auto max-w-2xl px-6 py-12 sm:px-8">
      <header className="mb-8 space-y-3">
        <h1 className="text-3xl font-semibold tracking-tight text-surface-foreground">
          {title}
        </h1>
        <p className="text-base text-surface-subtle">{description}</p>
        {quota && !quotaLoading ? <AnalysisQuotaChip quota={quota} /> : null}
      </header>
      <div className="rounded-2xl border border-surface-border bg-surface p-6 shadow-sm">
        {atLimit ? (
          <div className="space-y-3">
            <p className="text-sm text-warning-strong" role="status">
              You have reached the limit of {quota?.limit} active analyses. Delete
              a finished run from your history to free a slot.
            </p>
            <Link
              href="/analyses"
              className="inline-block text-sm font-medium text-primary-strong underline underline-offset-2"
            >
              Open your analyses
            </Link>
          </div>
        ) : (
          <UrlForm />
        )}
      </div>
    </div>
  )
}
