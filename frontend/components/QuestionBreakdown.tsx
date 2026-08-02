'use client'

import { useState } from 'react'
import { engineLabel } from '@/lib/engines'
import type { QuestionGroup } from '@/lib/results'

interface QuestionBreakdownProps {
  groups: QuestionGroup[]
  // Every engine the run should have covered, so the denominator is the panel
  // rather than however many answers happened to come back.
  engines: string[]
}

// The question-level view of a run: one card per question buyers ask, showing
// which engines named the brand in their answer. Replaces the flat response
// table, where each question repeated once per engine.
export default function QuestionBreakdown({
  groups,
  engines,
}: QuestionBreakdownProps) {
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
      {/* "goes to", not "was asked to": an engine with no rows may have failed
          mid-run, or may not have been on the panel for it, and the envelope
          does not say which. Claiming it was asked settles a question the data
          leaves open.

          Three entries because the grid renders three chip states. The middle
          one is an answer that left the brand out — the ordinary miss, and on a
          low-scoring run most of the grid. Folding it into "no answer came
          back" would read an outage into what is really a bad score. The marks
          carry the same aria-hidden / sr-only split as the chips they explain,
          so a screen reader hears the states rather than the glyphs. */}
      <p className="text-sm text-surface-subtle">
        Each question goes to every engine on the panel:{' '}
        <span aria-hidden="true">
          ✓ named you in its answer, ✕ answered without naming you, – no answer
          came back.
        </span>
        <span className="sr-only">
          a green engine named you in its answer, a solid grey engine answered
          without naming you, and a dashed outline means no answer came back.
        </span>
      </p>

      <ul className="space-y-3">
        {groups.map((group) => {
          const { prompt, responses, mentioned, snippet } = group
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
                    aria-hidden="true"
                    className={`block text-lg font-semibold tabular-nums ${
                      hit ? 'text-success-strong' : 'text-surface-subtle'
                    }`}
                  >
                    {mentioned}/{engines.length}
                  </span>
                  <span
                    aria-hidden="true"
                    className="text-xs uppercase tracking-wider text-surface-subtle"
                  >
                    engines
                  </span>
                  <span className="sr-only">
                    named you in {mentioned} of {engines.length} answers
                  </span>
                </p>
              </div>

              {/* One chip per panel engine, not per answer: an engine that
                  never answered this question is shown as a gap instead of
                  being left out of the count. */}
              <ul className="flex flex-wrap gap-2">
                {engines.map((engine) => {
                  const response = responses.find((row) => row.engine === engine)
                  const named = Boolean(response?.footprint)
                  const answered = Boolean(response)

                  return (
                    <li
                      key={engine}
                      className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-sm ${
                        named
                          ? 'border-success bg-success-soft font-medium text-success-strong'
                          : answered
                            ? 'border-surface-border bg-surface-muted text-surface-subtle'
                            : 'border-dashed border-surface-border bg-transparent text-surface-subtle'
                      }`}
                    >
                      <span aria-hidden="true">
                        {named ? '✓' : answered ? '✕' : '–'}
                      </span>
                      {engineLabel(engine)}
                      <span className="sr-only">
                        {named
                          ? 'named you'
                          : answered
                            ? 'did not name you'
                            : // Not "did not answer": that would assert this
                              // engine was asked and failed to reply.
                              'no answer'}
                      </span>
                    </li>
                  )
                })}
              </ul>

              {/* The evidence behind the ✓s, quoted from the first answer that
                  matched. A question nobody answered with a mention has no
                  snippet, and gets none. */}
              {snippet ? (
                <p className="truncate border-l-2 border-success-soft pl-3 text-xs text-surface-subtle">
                  “{snippet}”
                </p>
              ) : null}

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
                      {response.matched_snippet?.trim() ? (
                        <p className="border-l-2 border-success-soft pl-3 text-xs text-success-strong">
                          “{response.matched_snippet}”
                        </p>
                      ) : null}
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
      className={`h-3 w-3 shrink-0 motion-safe:transition-transform ${
        open ? 'rotate-90' : ''
      }`}
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
