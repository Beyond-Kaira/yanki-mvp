// Read-time aggregates the results screen needs but the MVP envelope does not
// carry. Both are plain arithmetic over `responses`, which already holds the
// model slug that produced each answer and whether the brand was found in it —
// no value here is invented, and nothing re-implements backend detection logic.

import type { AnalysisResponse, EnginePresence, Prompt } from './contracts'
import { GEO_LLM_MODELS, responseModelId } from './engines'

// The models a run should have covered: the configured fan-out list, plus
// anything that actually answered. Deriving purely from responses would erase
// a model that returned nothing for the whole run — an outage would silently
// shrink the denominator instead of showing up as a gap.
//
// The configured half is the build-time default (see engines.ts), so a deploy
// that overrides GEO_LLM_MODELS at runtime can list a model it never queried.
// That is the visible failure, and the quiet one is worse.
export function runEngineIds(
  responses: AnalysisResponse[],
  reported?: EnginePresence[] | null,
  configuredModels: string[] = GEO_LLM_MODELS,
): string[] {
  const seen = new Set<string>(configuredModels)
  for (const response of responses) seen.add(responseModelId(response))
  for (const stat of reported ?? []) seen.add(stat.engine)
  return [...seen]
}

// One path for both surfaces. The backend computes `engine_presence` for
// checker rows only, grouping by model slug; its aggregate walks the
// responses it has, so a model that answered nothing is missing from that list
// exactly as it would be from a naive local count.
//
// Taking the reported numbers as authoritative while seeding the roster from
// the configured list keeps the same guarantee on both screens: whoever did
// the counting, a model with no answers is listed rather than dropped, so an
// outage cannot quietly shrink the denominator on one surface and not the other.
export function deriveEnginePresence(
  responses: AnalysisResponse[],
  reported?: EnginePresence[] | null,
  configuredModels: string[] = GEO_LLM_MODELS,
): EnginePresence[] {
  const byEngine = new Map<string, { mentioned: number; total: number }>(
    runEngineIds(responses, reported, configuredModels).map((engine) => [
      engine,
      { mentioned: 0, total: 0 },
    ]),
  )

  if (reported) {
    for (const stat of reported) {
      byEngine.set(stat.engine, {
        mentioned: stat.mentioned,
        total: stat.total,
      })
    }
  } else {
    for (const response of responses) {
      const id = responseModelId(response)
      const stat = byEngine.get(id) ?? { mentioned: 0, total: 0 }
      stat.total += 1
      if (response.footprint) stat.mentioned += 1
      byEngine.set(id, stat)
    }
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
