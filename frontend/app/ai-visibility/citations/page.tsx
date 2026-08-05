'use client'

import { useState } from 'react'
import AnalysisBoundSubpage from '@/components/ai-visibility/AnalysisBoundSubpage'
import { citationsFromAnalysis } from '@/lib/ai-visibility-data'

function pct(value: number | null): string {
  if (value == null) return 'N/A'
  return `${Math.round(value * 1000) / 10}%`
}

export default function CitationsPage() {
  return (
    <AnalysisBoundSubpage title="Citations">
      {(analysis) => {
        const model = citationsFromAnalysis(analysis)
        return <CitationsContent model={model} />
      }}
    </AnalysisBoundSubpage>
  )
}

function CitationsContent({
  model,
}: {
  model: ReturnType<typeof citationsFromAnalysis>
}) {
  const [openDomain, setOpenDomain] = useState<string | null>(null)
  const summaryCards = [
    { label: 'Cite rate', value: pct(model.summary.citeRate) },
    { label: 'Owned rate', value: pct(model.summary.ownedRate) },
    { label: 'Earned rate', value: pct(model.summary.earnedRate) },
    {
      label: 'Avg citations',
      value:
        model.summary.avgCitations == null
          ? 'N/A'
          : String(Math.round(model.summary.avgCitations * 10) / 10),
    },
  ]

  return (
    <>
      <p className="text-sm text-surface-subtle">
        Sources cited across the measured run for{' '}
        <span className="font-medium text-surface-foreground">{model.domain}</span>
        {model.summary.recordCount != null
          ? ` · ${model.summary.recordCount} prompt records`
          : null}
      </p>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {summaryCards.map((card) => (
          <div
            key={card.label}
            className="rounded-xl border border-surface-border bg-surface px-4 py-3 shadow-sm"
          >
            <p className="text-xs uppercase tracking-wide text-surface-subtle">
              {card.label}
            </p>
            <p className="mt-1 text-2xl font-semibold tabular-nums text-surface-foreground">
              {card.value}
            </p>
          </div>
        ))}
      </div>

      {model.domains.length === 0 ? (
        <p className="rounded-xl border border-dashed border-surface-border px-4 py-8 text-center text-sm text-surface-subtle">
          No citation domains were recorded for this analysis.
        </p>
      ) : (
        <div className="overflow-hidden rounded-xl border border-surface-border bg-surface shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="bg-surface-muted text-xs uppercase tracking-wide text-surface-subtle">
              <tr>
                <th className="px-4 py-2.5 font-medium">Domain</th>
                <th className="px-4 py-2.5 text-right font-medium">Count</th>
                <th className="px-4 py-2.5 text-right font-medium">Sources</th>
              </tr>
            </thead>
            <tbody>
              {model.domains.map((row) => {
                const open = openDomain === row.domain
                return (
                  <tr key={row.domain} className="border-t border-surface-border">
                    <td className="px-4 py-3 align-top" colSpan={open ? 3 : 1}>
                      <button
                        type="button"
                        className="flex w-full items-center gap-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                        aria-expanded={open}
                        onClick={() =>
                          setOpenDomain(open ? null : row.domain)
                        }
                      >
                        <span
                          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary-soft text-[11px] font-semibold text-primary-strong"
                          aria-hidden
                        >
                          {row.domain.slice(0, 1).toUpperCase()}
                        </span>
                        <span className="font-medium text-surface-foreground">
                          {row.domain}
                        </span>
                      </button>
                      {open && row.urls.length > 0 ? (
                        <ul className="mt-3 space-y-2 border-t border-surface-border pt-3">
                          {row.urls.map((item, index) => (
                            <li
                              key={`${row.domain}-${item.url ?? index}`}
                              className="text-sm text-surface-subtle"
                            >
                              {item.title ? (
                                <p className="font-medium text-surface-foreground">
                                  {item.title}
                                </p>
                              ) : null}
                              {item.url ? (
                                <a
                                  href={item.url}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="break-all text-primary hover:text-primary-hover"
                                >
                                  {item.url}
                                </a>
                              ) : null}
                              <p className="mt-0.5 text-xs text-surface-subtle">
                                {[
                                  item.sourceType,
                                  item.mentionsBrand === true
                                    ? 'mentions brand'
                                    : item.mentionsBrand === false
                                      ? 'no brand mention'
                                      : null,
                                ]
                                  .filter(Boolean)
                                  .join(' · ')}
                              </p>
                            </li>
                          ))}
                        </ul>
                      ) : null}
                      {open && row.urls.length === 0 ? (
                        <p className="mt-3 border-t border-surface-border pt-3 text-sm text-surface-subtle">
                          Domain counted without individual URLs.
                        </p>
                      ) : null}
                    </td>
                    {!open ? (
                      <>
                        <td className="px-4 py-3 text-right tabular-nums text-surface-subtle">
                          {row.count}
                        </td>
                        <td className="px-4 py-3 text-right tabular-nums text-surface-subtle">
                          {row.urls.length}
                        </td>
                      </>
                    ) : null}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
