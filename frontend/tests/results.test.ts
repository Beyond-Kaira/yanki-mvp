import { describe, it, expect } from 'vitest'
import {
  deriveEnginePresence,
  groupByQuestion,
  runEngineIds,
} from '@/lib/results'
import type { AnalysisResponse, Prompt } from '@/lib/contracts'

// No casts: fixtures satisfy the generated wire types in full, so a contract
// change fails the build here rather than passing silently.
function response(overrides: Partial<AnalysisResponse>): AnalysisResponse {
  return {
    id: 'r1',
    engine: 'openai',
    model: 'mock',
    footprint: false,
    matched_snippet: null,
    prompt_id: 'p1',
    raw_text: 'answer',
    cost_usd: 0,
    ...overrides,
  }
}

const prompts: Prompt[] = [
  { id: 'p1', category: 'recommendation', text: 'Best analytics tools?' },
  { id: 'p2', category: 'comparison', text: 'How do they compare?' },
]

describe('runEngineIds', () => {
  it('covers the panel even when a run has no answers at all', () => {
    expect(runEngineIds([])).toEqual([
      'anthropic',
      'openai',
      'gemini',
      'perplexity',
    ])
  })

  it('includes an engine outside the panel that did answer', () => {
    expect(runEngineIds([response({ engine: 'mistral' })])).toContain('mistral')
  })
})

describe('deriveEnginePresence', () => {
  it('counts mentions per engine', () => {
    const presence = deriveEnginePresence([
      response({ id: 'a', engine: 'openai', footprint: true }),
      response({ id: 'b', engine: 'openai', footprint: false }),
      response({ id: 'c', engine: 'anthropic', footprint: true }),
    ])

    expect(presence).toContainEqual({
      engine: 'openai',
      mentioned: 1,
      total: 2,
    })
    expect(presence).toContainEqual({
      engine: 'anthropic',
      mentioned: 1,
      total: 1,
    })
  })

  it('keeps an engine that returned nothing instead of dropping it', () => {
    const presence = deriveEnginePresence([
      response({ id: 'a', engine: 'openai', footprint: true }),
    ])

    // A silent provider must not shrink the denominator: it reports 0 of 0.
    expect(presence).toContainEqual({
      engine: 'gemini',
      mentioned: 0,
      total: 0,
    })
    expect(presence).toHaveLength(4)
  })

  it('keeps the reported numbers while still seeding the roster', () => {
    // What the checker route gets: the backend aggregate walks the responses it
    // has, so an engine that answered nothing is absent from it entirely.
    const presence = deriveEnginePresence(
      [response({ id: 'a', engine: 'openai', footprint: true })],
      [{ engine: 'openai', mentioned: 7, total: 12 }],
    )

    // Reported numbers win: the backend can count rows this client never sees.
    expect(presence).toContainEqual({ engine: 'openai', mentioned: 7, total: 12 })
    // And the silent engine is still listed, which is the whole guarantee.
    expect(presence).toContainEqual({ engine: 'gemini', mentioned: 0, total: 0 })
    expect(presence).toHaveLength(4)
  })

  it('keeps a reported engine that is not on the panel', () => {
    const presence = deriveEnginePresence(
      [],
      [{ engine: 'mistral', mentioned: 1, total: 3 }],
    )

    expect(presence).toContainEqual({ engine: 'mistral', mentioned: 1, total: 3 })
  })

  it('treats a null footprint as not mentioned', () => {
    const presence = deriveEnginePresence([
      response({ id: 'a', engine: 'gemini', footprint: null }),
    ])

    expect(presence).toContainEqual({
      engine: 'gemini',
      mentioned: 0,
      total: 1,
    })
  })
})

describe('groupByQuestion', () => {
  it('groups responses under their prompt, in prompt order', () => {
    const groups = groupByQuestion(prompts, [
      response({ id: 'a', prompt_id: 'p2', engine: 'openai', footprint: true }),
      response({ id: 'b', prompt_id: 'p1', engine: 'openai', footprint: true }),
      response({
        id: 'c',
        prompt_id: 'p1',
        engine: 'anthropic',
        footprint: false,
      }),
    ])

    expect(groups.map((group) => group.prompt.id)).toEqual(['p1', 'p2'])
    expect(groups[0].responses.map((row) => row.id)).toEqual(['b', 'c'])
    expect(groups[0].mentioned).toBe(1)
    expect(groups[1].mentioned).toBe(1)
  })

  it('quotes the first snippet among the mentions', () => {
    const groups = groupByQuestion([prompts[0]], [
      response({ id: 'a', footprint: false, matched_snippet: 'ignored' }),
      response({ id: 'b', footprint: true, matched_snippet: '  ' }),
      response({ id: 'c', footprint: true, matched_snippet: 'Acme is named.' }),
    ])

    expect(groups[0].snippet).toBe('Acme is named.')
  })

  it('has no snippet when nothing matched', () => {
    const groups = groupByQuestion([prompts[0]], [
      response({ id: 'a', footprint: false }),
    ])

    expect(groups[0].snippet).toBeNull()
  })

  it('keeps a prompt that has no responses yet', () => {
    const groups = groupByQuestion(prompts, [])

    expect(groups).toHaveLength(2)
    expect(groups[0].responses).toEqual([])
    expect(groups[0].mentioned).toBe(0)
  })
})
