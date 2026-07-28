// Read-time aggregates the results screen needs but the MVP envelope does not
// carry. Both are plain arithmetic over `responses`, which already holds the
// engine that produced each answer and whether the brand was found in it — no
// value here is invented, and nothing re-implements backend detection logic.

import type { AnalysisResponse, EnginePresence, Prompt } from './contracts'
import { PANEL_ENGINE_IDS } from './engines'

// The engines a run should have covered: the panel, plus anything that actually
// answered. Deriving purely from responses would erase an engine that returned
// nothing for the whole run — an outage would silently shrink the denominator
// instead of showing up as a gap.
//
// The panel half is the build-time default (see engines.ts), so a deploy that
// overrides PANEL_ENGINES at runtime can list an engine it never queried. That
// is the visible failure, and the quiet one is worse.
export function runEngineIds(responses: AnalysisResponse[]): string[] {
  const seen = new Set(PANEL_ENGINE_IDS)
  for (const response of responses) seen.add(response.engine)
  return [...seen]
}

// The backend computes `engine_presence` only for checker rows (see
// `_to_out` in backend/app/api/routes.py), so an MVP analysis gets it null.
// Derive the same shape locally rather than leaving the section blank.
export function deriveEnginePresence(
  responses: AnalysisResponse[],
): EnginePresence[] {
  // Seeded with every engine the run should have covered, so one that answered
  // nothing reports 0 of 0 rather than vanishing from the list.
  const byEngine = new Map<string, { mentioned: number; total: number }>(
    runEngineIds(responses).map((engine) => [engine, { mentioned: 0, total: 0 }]),
  )

  for (const response of responses) {
    const stat = byEngine.get(response.engine) ?? { mentioned: 0, total: 0 }
    stat.total += 1
    if (response.footprint) stat.mentioned += 1
    byEngine.set(response.engine, stat)
  }

  return [...byEngine.entries()].map(([engine, stat]) => ({ engine, ...stat }))
}

export interface QuestionGroup {
  prompt: Prompt
  responses: AnalysisResponse[]
  // How many of this question's answers named the brand.
  mentioned: number
  // The first non-empty snippet among this question's mentions — the evidence
  // shown on the collapsed card. Null when nothing matched, so a miss never
  // gets a quote it cannot support.
  snippet: string | null
}

// One group per question instead of one row per (question × engine): the flat
// table repeated every question once per engine, which buried what a reader
// actually wants — the questions they show up on, and the ones they miss.
//
// Grouping is keyed off the prompt list, so a response whose prompt is missing
// from the envelope is left out; that pairing is guaranteed by the backend
// (responses reference prompts of the same analysis).
export function groupByQuestion(
  prompts: Prompt[],
  responses: AnalysisResponse[],
): QuestionGroup[] {
  const byPrompt = new Map<string, AnalysisResponse[]>()

  for (const response of responses) {
    const bucket = byPrompt.get(response.prompt_id)
    if (bucket) {
      bucket.push(response)
    } else {
      byPrompt.set(response.prompt_id, [response])
    }
  }

  return prompts.map((prompt) => {
    const promptResponses = byPrompt.get(prompt.id) ?? []
    const hits = promptResponses.filter((response) => response.footprint)
    const snippet = hits
      .map((response) => response.matched_snippet?.trim())
      .find((text): text is string => Boolean(text))

    return {
      prompt,
      responses: promptResponses,
      mentioned: hits.length,
      snippet: snippet ?? null,
    }
  })
}
