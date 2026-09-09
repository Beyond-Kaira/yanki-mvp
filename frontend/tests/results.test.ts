import { describe, it, expect } from 'vitest'
import {
  deriveEnginePresence,
  groupByQuestion,
  runEngineIds,
} from '@/lib/results'
import { GEO_LLM_MODELS } from '@/lib/engines'
import type { AnalysisResponse, Prompt } from '@/lib/contracts'
import { samplePrompt } from './analysisMocks'

// No casts: fixtures satisfy the generated wire types in full, so a contract
// change fails the build here rather than passing silently.
function response(overrides: Partial<AnalysisResponse>): AnalysisResponse {
  return {
    id: 'r1',
    llm_provider: 'openrouter',
    model: 'openai/gpt-4o-mini',
    footprint: false,
    matched_snippet: null,
    prompt_id: 'p1',
    raw_text: 'answer',
    cost_usd: 0,
    ...overrides,
  }
}

const prompts: Prompt[] = [
  samplePrompt({ id: 'p1', category: 'recommendation', text: 'Best analytics tools?' }),
  samplePrompt({ id: 'p2', category: 'comparison', text: 'How do they compare?' }),
]

describe('runEngineIds', () => {
  it('covers the configured models even when a run has no answers at all', () => {
    expect(runEngineIds([])).toEqual(GEO_LLM_MODELS)
  })

  it('includes a model outside the default list that did answer', () => {
    expect(
      runEngineIds([
        response({ llm_provider: 'openrouter', model: 'mistral/mistral-small' }),
      ]),
    ).toContain('mistral/mistral-small')
  })
})

describe('deriveEnginePresence', () => {
  it('counts mentions per model slug', () => {
    const presence = deriveEnginePresence([
      response({
        id: 'a',
        model: 'openai/gpt-4o-mini',
        footprint: true,
      }),
      response({
        id: 'b',
        model: 'openai/gpt-4o-mini',
        footprint: false,
      }),
      response({
        id: 'c',
        model: 'anthropic/claude-sonnet-4.5',
        footprint: true,
      }),
    ])

    expect(presence).toContainEqual({
      engine: 'openai/gpt-4o-mini',
      mentioned: 1,
      total: 2,
    })
    expect(presence).toContainEqual({
      engine: 'anthropic/claude-sonnet-4.5',
      mentioned: 1,
      total: 1,
    })
  })

  it('keeps a model that returned nothing instead of dropping it', () => {
    const presence = deriveEnginePresence([
      response({ id: 'a', model: 'openai/gpt-4o-mini', footprint: true }),
    ])

    expect(presence).toContainEqual({
      engine: 'google/gemini-2.5-flash',
      mentioned: 0,
      total: 0,
    })
    expect(presence).toHaveLength(GEO_LLM_MODELS.length)
  })

  it('keeps the reported numbers while still seeding the roster', () => {
    const presence = deriveEnginePresence(
      [response({ id: 'a', model: 'openai/gpt-4o-mini', footprint: true })],
      [{ engine: 'openai/gpt-4o-mini', mentioned: 7, total: 12 }],
    )

    expect(presence).toContainEqual({
      engine: 'openai/gpt-4o-mini',
      mentioned: 7,
      total: 12,
    })
    expect(presence).toContainEqual({
      engine: 'google/gemini-2.5-flash',
      mentioned: 0,
      total: 0,
    })
    expect(presence).toHaveLength(GEO_LLM_MODELS.length)
  })

  it('keeps a reported model that is not on the default list', () => {
    const presence = deriveEnginePresence(
      [],
      [{ engine: 'mistral/mistral-small', mentioned: 1, total: 3 }],
    )

    expect(presence).toContainEqual({
      engine: 'mistral/mistral-small',
      mentioned: 1,
      total: 3,
    })
  })

  it('treats a null footprint as not mentioned', () => {
    const presence = deriveEnginePresence([
      response({
        id: 'a',
        model: 'google/gemini-2.5-flash',
        footprint: null,
      }),
    ])

    expect(presence).toContainEqual({
      engine: 'google/gemini-2.5-flash',
      mentioned: 0,
      total: 1,
    })
  })

  it('falls back to llm_provider when model is mock (legacy rows)', () => {
    const presence = deriveEnginePresence([
      response({
        id: 'a',
        llm_provider: 'anthropic',
        model: 'mock',
        footprint: true,
      }),
    ])

    expect(presence).toContainEqual({
      engine: 'anthropic',
      mentioned: 1,
      total: 1,
    })
  })
})

describe('groupByQuestion', () => {
  it('groups responses under their prompt, in prompt order', () => {
    const groups = groupByQuestion(prompts, [
      response({ id: 'a', prompt_id: 'p2', model: 'openai/gpt-4o-mini', footprint: true }),
      response({ id: 'b', prompt_id: 'p1', model: 'openai/gpt-4o-mini', footprint: true }),
      response({
        id: 'c',
        prompt_id: 'p1',
        model: 'anthropic/claude-sonnet-4.5',
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
