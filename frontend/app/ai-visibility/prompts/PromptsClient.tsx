'use client'

import AnalysisBoundSubpage from '@/components/ai-visibility/AnalysisBoundSubpage'
import QuestionBreakdown from '@/components/QuestionBreakdown'
import { promptsFromAnalysis } from '@/lib/ai-visibility-data'

export default function PromptsPage() {
  return (
    <AnalysisBoundSubpage title="Prompts & Answers">
      {(analysis) => {
        const model = promptsFromAnalysis(analysis)
        const hasLegacy = model.groups.length > 0
        const hasGeo = model.geoPromptRows.length > 0

        return (
          <>
            <p className="text-sm text-surface-subtle">
              Measured run for{' '}
              <span className="font-medium text-surface-foreground">
                {model.domain}
              </span>
            </p>

            {hasLegacy ? (
              <QuestionBreakdown
                groups={model.groups}
                engines={model.engines}
              />
            ) : null}

            {hasGeo ? (
              <section className="space-y-3" aria-labelledby="geo-prompts-heading">
                <h2
                  id="geo-prompts-heading"
                  className="text-xl font-semibold text-surface-foreground"
                >
                  {hasLegacy ? 'Measured prompt records' : 'Prompts & grounded answers'}
                </h2>
                <ul className="space-y-3">
                  {model.geoPromptRows.map((row) => (
                    <li
                      key={row.id}
                      className="rounded-xl border border-surface-border bg-surface p-4 shadow-sm"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="flex-1 text-sm font-medium text-surface-foreground">
                          {row.prompt}
                        </p>
                        {row.mentioned == null ? null : (
                          <span
                            className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                              row.mentioned
                                ? 'bg-success-soft text-success-strong'
                                : 'bg-surface-muted text-surface-subtle'
                            }`}
                          >
                            {row.mentioned ? 'Mentioned' : 'Not mentioned'}
                          </span>
                        )}
                        {row.mentionContext ? (
                          <span className="rounded-full bg-primary-soft px-2 py-0.5 text-[11px] font-medium text-primary-strong">
                            {row.mentionContext.replace(/_/g, ' ')}
                          </span>
                        ) : null}
                        {row.sentiment ? (
                          <span className="text-[11px] uppercase tracking-wide text-surface-subtle">
                            {row.sentiment}
                          </span>
                        ) : null}
                      </div>
                      {row.answer ? (
                        <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-surface-subtle">
                          {row.answer}
                        </p>
                      ) : (
                        <p className="mt-3 text-sm text-surface-subtle">
                          No grounded answer stored for this prompt.
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}

            {!hasLegacy && !hasGeo ? (
              <p className="rounded-xl border border-dashed border-surface-border px-4 py-8 text-center text-sm text-surface-subtle">
                No prompts or answers were recorded for this analysis.
              </p>
            ) : null}
          </>
        )
      }}
    </AnalysisBoundSubpage>
  )
}
