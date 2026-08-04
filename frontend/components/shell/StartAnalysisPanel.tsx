'use client'

import UrlForm from '@/components/UrlForm'

/** Empty-state for product shell: start a domain analysis (not sample metrics). */
export default function StartAnalysisPanel({
  title = 'Run an analysis',
  description = 'Enter your company domain. We crawl the site, ask AI engines about your brand, and build your GEO score.',
}: {
  title?: string
  description?: string
}) {
  return (
    <div className="mx-auto max-w-2xl px-6 py-12 sm:px-8">
      <header className="mb-8 space-y-3">
        <h1 className="text-3xl font-semibold tracking-tight text-surface-foreground">
          {title}
        </h1>
        <p className="text-base text-surface-subtle">{description}</p>
      </header>
      <div className="rounded-2xl border border-surface-border bg-surface p-6 shadow-sm">
        <UrlForm />
      </div>
    </div>
  )
}
