'use client'

import { useEffect, useState } from 'react'
import { formatCount, formatMetric } from '@/components/backlinks/backlinkUtils'
import EmptyPanel from '@/components/site-audit/shared/EmptyPanel'
import { getBacklinkOpportunities } from '@/lib/api'
import type { BacklinkOpportunities } from '@/lib/contracts'

export default function OpportunitiesPanel({ projectId }: { projectId: string }) {
  const [data, setData] = useState<BacklinkOpportunities | null>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [message, setMessage] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false
    setStatus('loading')

    getBacklinkOpportunities(projectId, controller.signal)
      .then((result) => {
        if (cancelled) return
        setData(result)
        setStatus('ready')
      })
      .catch((error: unknown) => {
        if (cancelled || (error instanceof Error && error.name === 'AbortError')) {
          return
        }
        setMessage(
          error instanceof Error
            ? error.message
            : 'Opportunities could not be loaded.',
        )
        setStatus('error')
      })

    return () => {
      cancelled = true
      controller.abort()
    }
  }, [projectId])

  if (status === 'loading') {
    return (
      <p
        role="status"
        className="rounded-xl border border-surface-border bg-surface p-6 text-sm text-surface-subtle sm:p-8"
      >
        Loading opportunities…
      </p>
    )
  }

  if (status === 'error' || !data) {
    return (
      <section className="overflow-hidden rounded-xl border border-surface-border bg-surface shadow-sm">
        <EmptyPanel title="Opportunities could not be loaded" message={message} />
      </section>
    )
  }

  const gap = data.link_gap ?? []
  const mentions = data.unlinked_mentions ?? []

  return (
    <div className="space-y-4">
      <section className="overflow-hidden rounded-xl border border-surface-border bg-surface shadow-sm">
        <div className="border-b border-surface-border px-5 py-4 sm:px-6">
          <h2 className="text-xl font-semibold text-surface-foreground">
            Link gap
          </h2>
          <p className="mt-1 text-sm text-surface-subtle">
            Domains linking to competitors but not to you, ranked by how many
            rivals earned the link and how strong the domain is.
          </p>
          {data.provenance?.link_gap ? (
            <p className="mt-2 text-xs text-surface-subtle">
              Source: {data.provenance.link_gap}
            </p>
          ) : null}
        </div>

        {!gap.length ? (
          <EmptyPanel
            title="No gap results"
            message="Track competitor domains for this project, then refresh — the gap is computed against their profiles."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-[720px] w-full border-collapse text-left text-sm">
              <caption className="sr-only">
                Referring domains linking to tracked competitors but not to this
                project
              </caption>
              <thead className="bg-surface-zebra text-xs font-medium uppercase tracking-wide text-surface-subtle">
                <tr>
                  <th scope="col" className="px-5 py-3 sm:px-6">Domain</th>
                  <th scope="col" className="px-4 py-3">Competitors linking</th>
                  <th scope="col" className="px-4 py-3">Authority</th>
                  <th scope="col" className="px-5 py-3 sm:px-6">Score</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-border">
                {gap.map((row) => (
                  <tr key={row.referring_domain} className="align-top">
                    <th scope="row" className="px-5 py-4 font-medium sm:px-6">
                      {row.referring_domain}
                    </th>
                    <td className="px-4 py-4 text-surface-foreground">
                      {formatCount(row.linking_competitors)}
                      <span className="mt-0.5 block text-xs text-surface-subtle">
                        {(row.competitor_domains ?? []).join(', ')}
                      </span>
                    </td>
                    <td className="px-4 py-4 text-surface-foreground">
                      {formatMetric(
                        row.domain_authority === null ||
                          row.domain_authority === undefined
                          ? null
                          : Math.round(row.domain_authority),
                      )}
                    </td>
                    <td className="px-5 py-4 text-surface-foreground sm:px-6">
                      {row.score.toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="overflow-hidden rounded-xl border border-surface-border bg-surface shadow-sm">
        <div className="border-b border-surface-border px-5 py-4 sm:px-6">
          <h2 className="text-xl font-semibold text-surface-foreground">
            Unlinked mentions
          </h2>
          <p className="mt-1 text-sm text-surface-subtle">
            Pages that already talked about the brand without linking to it —
            usually the easiest link to earn.
          </p>
          {/* Worth naming: this list costs nothing to produce because it is
              read from citation and SERP evidence Yanki already has. A link-only
              tool cannot build it at all. */}
          {data.provenance?.unlinked_mentions ? (
            <p className="mt-2 text-xs text-surface-subtle">
              Source: {data.provenance.unlinked_mentions}
            </p>
          ) : null}
        </div>

        {!mentions.length ? (
          <EmptyPanel
            title="No unlinked mentions found"
            message="These come from this project's own AI-citation and search evidence, so they appear once those have run."
          />
        ) : (
          <ul className="divide-y divide-surface-border">
            {mentions.map((mention) => (
              <li key={mention.source_url} className="px-5 py-4 sm:px-6">
                <a
                  href={mention.source_url}
                  target="_blank"
                  rel="noreferrer nofollow"
                  className="block truncate font-medium text-primary hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                >
                  {mention.source_domain}
                </a>
                <p className="mt-1 truncate text-xs text-surface-subtle">
                  {mention.source_url}
                </p>
                <p className="mt-1 text-xs text-surface-subtle">
                  Seen via {mention.seen_via}
                  {mention.evidence ? ` — ${mention.evidence}` : ''}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
