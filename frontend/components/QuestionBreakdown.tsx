'use client'

import { useState } from 'react'
import { engineLabel } from '@/lib/engines'
import type { QuestionGroup } from '@/lib/results'

interface QuestionBreakdownProps {
  groups: QuestionGroup[]
}

// The question-level view of a run: one card per question buyers ask, showing
// which engines named the brand in their answer. Replaces the flat response
// table, where each question repeated once per engine.
export default function QuestionBreakdown({ groups }: QuestionBreakdownProps) {
  // Collapsed by default; multiple questions may be open at once.
  const [openIds, setOpenIds] = useState<Set<string>>(() => new Set())

  function toggle(id: string) {
    setOpenIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  return (
    <section className="space-y-3" aria-labelledby="questions-heading">
      <h2
        id="questions-heading"
        className="text-xl font-semibold text-surface-foreground"
      >
        Question by question
      </h2>
      <p className="text-sm text-surface-subtle">
        Each question was asked to every engine on the panel. A green engine
        named you in its answer.
      </p>

      <ul className="space-y-3">
        {groups.map((group) => {
          const { prompt, responses, mentioned } = group
          const isOpen = openIds.has(prompt.id)
          const answersId = `answers-${prompt.id}`
          const hit = mentioned > 0

          return (
            <li
              key={prompt.id}
              className="space-y-3 rounded-xl border border-surface-border bg-white p-4"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-2">
                  <p className="font-medium leading-snug text-surface-foreground">
                    {prompt.text}
                  </p>
                  <span className="inline-block rounded-full bg-primary-soft px-2 py-0.5 text-xs font-medium text-primary-strong">
                    {prompt.category}
                  </span>
                </div>
                <p className="shrink-0 text-right">
                  <span
                    className={`block text-lg font-semibold tabular-nums ${
                      hit ? 'text-success-strong' : 'text-surface-subtle'
                    }`}
                  >
                    {mentioned}/{responses.length}
                  </span>
                  <span className="text-xs uppercase tracking-wider text-surface-subtle">
                    engines
                  </span>
                  <span className="sr-only">
                    named you in {mentioned} of {responses.length} answers
                  </span>
                </p>
              </div>

              <ul className="flex flex-wrap gap-2">
                {responses.map((response) => (
                  <li
                    key={response.id}
                    className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-sm ${
                      response.footprint
                        ? 'border-success-soft bg-success-soft font-medium text-success-strong'
                        : 'border-surface-border bg-surface-muted text-surface-subtle'
                    }`}
                  >
                    <span aria-hidden="true">
                      {response.footprint ? '✓' : '✕'}
                    </span>
                    {engineLabel(response.engine)}
                    <span className="sr-only">
                      {response.footprint ? 'named you' : 'did not name you'}
                    </span>
                  </li>
                ))}
              </ul>

              {responses.length > 0 ? (
                <button
                  type="button"
                  onClick={() => toggle(prompt.id)}
                  aria-expanded={isOpen}
                  aria-controls={answersId}
                  className="inline-flex min-h-[32px] items-center gap-1 rounded text-sm font-medium text-primary hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                >
                  <Chevron open={isOpen} />
                  {isOpen ? 'Hide answers' : 'Show answers'}
                </button>
              ) : null}

              {isOpen ? (
                <ul
                  id={answersId}
                  className="space-y-3 border-t border-surface-border pt-3"
                >
                  {responses.map((response) => (
                    <li key={`answer-${response.id}`} className="space-y-1">
                      <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-surface-foreground">
                        {engineLabel(response.engine)}
                        <span className="font-mono text-xs font-normal text-surface-subtle">
                          {response.model}
                        </span>
                      </p>
                      {response.raw_text.trim().length > 0 ? (
                        <pre className="max-w-prose whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-surface-foreground">
                          {response.raw_text}
                        </pre>
                      ) : (
                        <p className="text-xs italic text-surface-subtle">
                          (empty answer)
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              ) : null}
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 16 16"
      className={`h-3 w-3 shrink-0 transition-transform ${open ? 'rotate-90' : ''}`}
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M6 4l4 4-4 4" />
    </svg>
  )
}
