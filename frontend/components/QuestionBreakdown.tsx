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

// Collapsed by default; any number of ids may be open at once. Used twice:
// once for which question rows are expanded, once for which per-engine
// answers within them are — two independent sets, since opening a question
// should not force open (or remember) any engine's full answer.
function useToggleSet(): [Set<string>, (id: string) => void] {
  const [ids, setIds] = useState<Set<string>>(() => new Set())

  function toggle(id: string) {
    setIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  return [ids, toggle]
}

// The question-level view of a run: one row per question buyers ask, showing
// which engines named the brand in their answer. Replaces the flat response
// table, where each question repeated once per engine.
export default function QuestionBreakdown({
  groups,
  engines,
}: QuestionBreakdownProps) {
  const [openIds, toggle] = useToggleSet()
  const [openAnswerIds, toggleAnswer] = useToggleSet()

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

      {/* Laid out like a table (CSS grid columns), but marked up as a plain
          list: axe rejects role="row"/"cell" on elements without a real
          role="table" ancestor, and the native semantics here — a list of
          expandable rows, each with a button carrying aria-expanded /
          aria-controls — already say everything a screen reader needs. */}
      <div className="overflow-hidden rounded-xl border border-surface-border bg-white">
        <div
          className="grid grid-cols-[1fr_auto_auto] items-center gap-3 border-b border-surface-border bg-surface-muted px-4 py-2 text-xs font-medium uppercase tracking-wider text-surface-subtle"
          aria-hidden="true"
        >
          <span>Question</span>
          <span className="text-right">Engines</span>
          <span />
        </div>
        <ul className="divide-y divide-surface-border">
          {groups.map((group) => {
            const { prompt, responses, mentioned } = group
            const isOpen = openIds.has(prompt.id)
            const answersId = `answers-${prompt.id}`
            const hit = mentioned > 0

            return (
              <li key={prompt.id}>
                <div className="grid grid-cols-[1fr_auto_auto] items-center gap-3 px-4 py-3">
                  <div className="min-w-0 space-y-1.5">
                    {/* No truncate: the question is the reason the row exists,
                        so it wraps to however many lines it needs instead of
                        ending in an ellipsis a reader can't recover from. */}
                    <p className="font-medium leading-snug text-surface-foreground">
                      {prompt.text}
                    </p>
                    <span className="inline-block rounded-full bg-primary-soft px-2 py-0.5 text-xs font-medium text-primary-strong">
                      {prompt.category}
                    </span>
                  </div>
                  <p className="text-right">
                    <span
                      className={`text-sm font-semibold tabular-nums ${
                        hit ? 'text-success-strong' : 'text-surface-subtle'
                      }`}
                      aria-hidden="true"
                    >
                      {mentioned}/{engines.length}
                    </span>
                    {/* "engines", not "answers": the denominator is the panel
                        roster, so a run where two of four engines answered
                        would otherwise be read out as four answers. */}
                    <span className="sr-only">
                      {mentioned} of {engines.length} engines named you
                    </span>
                  </p>
                  <p>
                    {/* Icon-only: the row itself already reads as a toggle
                        (chip grid + answers folding in below it), so the
                        label would repeat what aria-expanded already says to
                        assistive tech. aria-label keeps the accessible name. */}
                    <button
                      type="button"
                      onClick={() => toggle(prompt.id)}
                      aria-expanded={isOpen}
                      aria-controls={answersId}
                      aria-label={isOpen ? 'Collapse' : 'Expand'}
                      className="inline-flex min-h-[32px] min-w-[32px] items-center justify-center rounded text-primary hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                    >
                      <Chevron open={isOpen} />
                    </button>
                  </p>
                </div>

                {isOpen ? (
                  <div
                    id={answersId}
                    className="space-y-3 border-t border-surface-border bg-surface-muted px-4 py-3"
                  >
                    {/* One chip per panel engine, not per answer: an engine
                        that never answered this question is shown as a gap
                        instead of being left out of the count. */}
                    <ul className="flex flex-wrap gap-2">
                      {engines.map((engine) => {
                        const response = responses.find(
                          (row) => row.engine === engine,
                        )
                        const named = Boolean(response?.footprint)
                        const answered = Boolean(response)

                        return (
                          <li
                            key={engine}
                            className={`inline-flex items-center gap-1.5 rounded-lg border bg-white px-2.5 py-1.5 text-sm ${
                              named
                                ? 'border-success bg-success-soft font-medium text-success-strong'
                                : answered
                                  ? 'border-surface-border text-surface-subtle'
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
                                  : // Not "did not answer": that would assert
                                    // this engine was asked and failed to
                                    // reply.
                                    'no answer'}
                            </span>
                          </li>
                        )
                      })}
                    </ul>

                    {/* One row per engine that actually answered — a second
                        expand level, nested inside the question's. The quote
                        (or the miss) is the thing worth reading at a glance;
                        the full transcript is one more click for whoever
                        wants to verify it, not something everyone scrolls
                        past by default. */}
                    <ul className="space-y-2">
                      {responses.map((response) => {
                        // Guarded and quoted from the same trimmed value.
                        // groupQuestions already trims the collapsed preview
                        // (lib/results.ts), so quoting the raw field here
                        // would put the same evidence on screen two different
                        // ways.
                        const evidence = response.matched_snippet?.trim()
                        const rawId = `raw-${response.id}`
                        const isRawOpen = openAnswerIds.has(response.id)

                        return (
                          <li
                            key={`answer-${response.id}`}
                            className="rounded-lg bg-white p-3"
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0 space-y-1">
                                <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-surface-foreground">
                                  {engineLabel(response.engine)}
                                  <span className="font-mono text-xs font-normal text-surface-subtle">
                                    {response.model}
                                  </span>
                                </p>
                                {evidence ? (
                                  <p className="truncate border-l-2 border-success-soft pl-3 text-xs text-success-strong">
                                    “{evidence}”
                                  </p>
                                ) : (
                                  <p className="pl-3 text-xs italic text-surface-subtle">
                                    did not name you
                                  </p>
                                )}
                              </div>
                              <button
                                type="button"
                                onClick={() => toggleAnswer(response.id)}
                                aria-expanded={isRawOpen}
                                aria-controls={rawId}
                                className="inline-flex min-h-[32px] shrink-0 items-center gap-1 whitespace-nowrap rounded px-1 text-xs font-medium text-primary hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                              >
                                <Chevron open={isRawOpen} />
                                {isRawOpen ? 'Hide full answer' : 'Show full answer'}
                              </button>
                            </div>
                            {isRawOpen ? (
                              <div
                                id={rawId}
                                className="mt-2 border-t border-surface-border pt-2"
                              >
                                {response.raw_text.trim().length > 0 ? (
                                  <pre className="max-w-prose whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-surface-foreground">
                                    {response.raw_text}
                                  </pre>
                                ) : (
                                  <p className="text-xs italic text-surface-subtle">
                                    (empty answer)
                                  </p>
                                )}
                              </div>
                            ) : null}
                          </li>
                        )
                      })}
                    </ul>
                  </div>
                ) : null}
              </li>
            )
          })}
        </ul>
      </div>
    </section>
  )
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 16 16"
      className={`h-4 w-4 shrink-0 motion-safe:transition-transform ${
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
