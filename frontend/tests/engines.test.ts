import { describe, it, expect } from 'vitest'
import methodology from '@/lib/checker_methodology.json'
import {
  GEO_LLM_MODELS,
  PANEL_ENGINE_IDS,
  engineLabel,
  engineVendorLabel,
  modelSlugLabel,
} from '@/lib/engines'

describe('engine identity', () => {
  it('takes the panel from the generated artifact', () => {
    expect(PANEL_ENGINE_IDS).toEqual(methodology.engines)
  })

  // The ids are generated from the backend registry, the display names are
  // still hand-kept here. That gap is the whole risk: an engine added to the
  // panel would reach every surface as a raw id until someone remembers to
  // teach both maps. This turns "someone forgets" from a silent leak into a
  // red test that names the missing engine.
  it.each(methodology.engines)('has both display names for %s', (id) => {
    expect(engineLabel(id)).not.toBe(id)
    expect(engineVendorLabel(id)).not.toBe(id)
  })

  it('falls back to the raw id for an engine it has not been taught', () => {
    // Not a failure mode to hide: showing `mistral` is honest, dropping the
    // engine from the screen is not.
    expect(engineLabel('mistral')).toBe('mistral')
    expect(engineVendorLabel('mistral')).toBe('mistral')
  })

  it('exports the default GEO multi-LLM fan-out from the generated artifact', () => {
    const fromArtifact = (methodology as { geo_llm_models?: string[] }).geo_llm_models
    expect(fromArtifact).toEqual([
      'openai/gpt-4o-mini',
      'anthropic/claude-sonnet-4.5',
      'google/gemini-2.5-flash',
    ])
    expect(GEO_LLM_MODELS).toEqual(fromArtifact)
  })

  it('labels known OpenRouter slugs with short product names', () => {
    expect(modelSlugLabel('openai/gpt-4o-mini')).toBe('GPT-4o mini')
    expect(modelSlugLabel('anthropic/claude-sonnet-4.5')).toBe('Claude Sonnet 4.5')
    expect(modelSlugLabel('google/gemini-2.5-flash')).toBe('Gemini 2.5 Flash')
  })

  it('prettifies unknown slugs instead of hiding them', () => {
    expect(modelSlugLabel('mistral/mistral-small')).toBe('mistral small')
  })
})
