import { describe, it, expect } from 'vitest'
import { deriveEnginePresence, groupByQuestion } from '@/lib/results'
import type { AnalysisResponse, Prompt } from '@/lib/contracts'

function response(overrides: Partial<AnalysisResponse>): AnalysisResponse {
  return {
    id: 'r1',
    engine: 'openai',
    model: 'mock',
    footprint: false,
    matched_snippet: null,
    prompt_id: 'p1',
    raw_text: 'answer',
    ...overrides,
  } as AnalysisResponse
}

const prompts: Prompt[] = [
  { id: 'p1', category: 'recommendation', text: 'Best analytics tools?' },
  { id: 'p2', category: 'comparison', text: 'How do they compare?' },
] as Prompt[]

describe('deriveEnginePresence', () => {
  it('counts mentions per engine', () => {
    const presence = deriveEnginePresence([
      response({ id: 'a', engine: 'openai', footprint: true }),
      response({ id: 'b', engine: 'openai', footprint: false }),
      response({ id: 'c', engine: 'anthropic', footprint: true }),
    ])

    expect(presence).toEqual([
      { engine: 'openai', mentioned: 1, total: 2 },
      { engine: 'anthropic', mentioned: 1, total: 1 },
    ])
  })

  it('treats a null footprint as not mentioned', () => {
    const presence = deriveEnginePresence([
      response({ id: 'a', engine: 'gemini', footprint: null }),
    ])

    expect(presence).toEqual([{ engine: 'gemini', mentioned: 0, total: 1 }])
  })

  it('returns nothing for an empty run', () => {
    expect(deriveEnginePresence([])).toEqual([])
  })
})

describe('groupByQuestion', () => {
  it('groups responses under their prompt, in prompt order', () => {
    const groups = groupByQuestion(prompts, [
      response({ id: 'a', prompt_id: 'p2', engine: 'openai', footprint: true }),
      response({ id: 'b', prompt_id: 'p1', engine: 'openai', footprint: true }),
      response({ id: 'c', prompt_id: 'p1', engine: 'anthropic', footprint: false }),
    ])

    expect(groups.map((group) => group.prompt.id)).toEqual(['p1', 'p2'])
    expect(groups[0].responses.map((r) => r.id)).toEqual(['b', 'c'])
    expect(groups[0].mentioned).toBe(1)
    expect(groups[1].mentioned).toBe(1)
  })

  it('keeps a prompt that has no responses yet', () => {
    const groups = groupByQuestion(prompts, [])

    expect(groups).toHaveLength(2)
    expect(groups[0].responses).toEqual([])
    expect(groups[0].mentioned).toBe(0)
  })
})
