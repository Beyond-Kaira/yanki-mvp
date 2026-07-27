// Read-time aggregates the results screen needs but the MVP envelope does not
// carry. Both are plain arithmetic over `responses`, which already holds the
// engine that produced each answer and whether the brand was found in it — no
// value here is invented, and nothing re-implements backend detection logic.

import type { AnalysisResponse, EnginePresence, Prompt } from './contracts'

// The backend computes `engine_presence` only for checker rows (see
// `_to_out` in backend/app/api/routes.py), so an MVP analysis gets it null.
// Derive the same shape locally rather than leaving the section blank.
export function deriveEnginePresence(
  responses: AnalysisResponse[],
): EnginePresence[] {
  const byEngine = new Map<string, { mentioned: number; total: number }>()

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
    return {
      prompt,
      responses: promptResponses,
      mentioned: promptResponses.filter((response) => response.footprint).length,
    }
  })
}
