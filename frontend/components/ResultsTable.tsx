'use client'

import { Fragment, useState } from 'react'
import type { AnalysisResponse, Prompt } from '@/lib/contracts'
import { engineLabel } from '@/lib/engines'

interface ResultsTableProps {
  responses: AnalysisResponse[]
  prompts: Prompt[]
}

// Five data columns plus the trailing toggle: the expanded answer row spans all.
const COLUMN_COUNT = 6

export default function ResultsTable({ responses, prompts }: ResultsTableProps) {
  const promptText = new Map(prompts.map((prompt) => [prompt.id, prompt.text]))
  // Collapsed by default; multiple rows may be open at once.
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
    <div className="overflow-x-auto rounded-xl border border-surface-border">
      <table className="w-full min-w-[640px] table-fixed border-collapse text-left text-sm">
        <thead>
          <tr className="bg-surface-muted text-xs font-medium uppercase tracking-wider text-surface-subtle">
            <th scope="col" className="w-[12%] px-4 py-3">
              Engine
            </th>
            <th scope="col" className="w-[16%] px-4 py-3">
              Model
            </th>
            <th scope="col" className="w-[10%] px-4 py-3">
              Footprint
            </th>
            <th scope="col" className="w-[26%] px-4 py-3">
              Matched snippet
            </th>
            <th scope="col" className="w-[24%] px-4 py-3">
              Prompt
            </th>
            <th scope="col" className="w-[12%] px-4 py-3">
              Answer
            </th>
          </tr>
        </thead>
        <tbody>
          {responses.map((response, index) => {
            const zebra = index % 2 === 1 ? 'bg-surface-zebra' : 'bg-white'
            const isOpen = openIds.has(response.id)
            const answerId = `answer-${response.id}`

            return (
              <Fragment key={response.id}>
                <tr className={zebra}>
                  <td className="px-4 py-3 font-medium text-surface-foreground">
                    {engineLabel(response.engine)}
                  </td>
                  <td className="px-4 py-3 text-surface-subtle">
                    <span className="block truncate" title={response.model}>
                      {response.model}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <FootprintBadge value={response.footprint} />
                  </td>
                  <td className="px-4 py-3">
                    {response.matched_snippet ? (
                      <span
                        className="block truncate font-mono text-xs text-surface-foreground"
                        title={response.matched_snippet}
                      >
                        {response.matched_snippet}
                      </span>
                    ) : (
                      <span className="text-xs text-surface-subtle">
                        Not mentioned in this answer.
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className="block truncate text-surface-subtle"
                      title={promptText.get(response.prompt_id) ?? ''}
                    >
                      {promptText.get(response.prompt_id) ?? '—'}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      onClick={() => toggle(response.id)}
                      aria-expanded={isOpen}
                      aria-controls={answerId}
                      className="inline-flex min-h-[32px] items-center gap-1 rounded text-xs font-medium text-primary hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                    >
                      <Chevron open={isOpen} />
                      {isOpen ? 'Hide full answer' : 'Show full answer'}
                    </button>
                  </td>
                </tr>
                {isOpen ? (
                  // Attaches to its parent row: same zebra fill, a subtle top border.
                  <tr className={zebra}>
                    <td
                      id={answerId}
                      colSpan={COLUMN_COUNT}
                      className="border-t border-surface-border px-4 pb-4 pt-1"
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
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
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

function FootprintBadge({ value }: { value: boolean | null }) {
  if (value) {
    return (
      <span className="inline-flex items-center rounded-full bg-success-soft px-2 py-1 text-xs font-medium text-success-strong">
        Yes
      </span>
    )
  }
  return (
    <span className="inline-flex items-center rounded-full bg-danger-soft px-2 py-1 text-xs font-medium text-danger-strong">
      No
    </span>
  )
}
