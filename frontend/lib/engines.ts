// Engine and model identity in one place: legacy panel ids, OpenRouter gateway,
// and multi-LLM model slugs. Every surface that names an engine or model reads
// from here — progress panel, results screens, answer tables, /methodology —
// so a label can never drift between two pages.

// Build-time import of the GENERATED artifact (scripts/gen_methodology.py, run
// by `make gen-types`), which carries the backend's DEFAULT_PANEL verbatim and
// the default GEO_LLM_MODELS fan-out list.
import methodology from './checker_methodology.json'
import type { AnalysisResponse } from './contracts'

export const PANEL_ENGINE_IDS: string[] = methodology.engines

/** Default OpenRouter model slugs for measured/simulated GEO (mirrors backend). */
export const GEO_LLM_MODELS: string[] =
  'geo_llm_models' in methodology &&
  Array.isArray((methodology as { geo_llm_models?: string[] }).geo_llm_models)
    ? (methodology as { geo_llm_models: string[] }).geo_llm_models
    : [
        'openai/gpt-4o-mini',
        'anthropic/claude-sonnet-4.5',
        'google/gemini-2.5-flash',
      ]

// Short product names: what a reader recognizes. Used where space is tight and
// the vendor adds nothing — legacy panel rows and the OpenRouter gateway label.
const ENGINE_LABELS: Record<string, string> = {
  anthropic: 'Claude',
  openai: 'ChatGPT',
  gemini: 'Gemini',
  perplexity: 'Perplexity',
  openrouter: 'OpenRouter',
}

// Vendor-qualified names: used where the vendor IS the information, i.e. the
// methodology page explaining which companies' models answer the prompts.
const ENGINE_VENDOR_LABELS: Record<string, string> = {
  anthropic: 'Anthropic (Claude)',
  openai: 'OpenAI (GPT)',
  gemini: 'Google (Gemini)',
  perplexity: 'Perplexity',
  openrouter: 'OpenRouter',
}

// OpenRouter slugs → short UI labels (UI group key = response.model).
const MODEL_SLUG_LABELS: Record<string, string> = {
  'openai/gpt-4o-mini': 'GPT-4o mini',
  'anthropic/claude-sonnet-4.5': 'Claude Sonnet 4.5',
  'google/gemini-2.5-flash': 'Gemini 2.5 Flash',
}

/** Group key for presence maps and chip grids — model slug, legacy panel id fallback. */
export function responseModelId(response: AnalysisResponse): string {
  const model = response.model?.trim()
  if (model && model !== 'mock') return model
  return response.llm_provider
}

// An id these maps have not been taught yet falls back to the raw value:
// showing `mistral` is honest, hiding the engine is not.
export function engineLabel(engine: string): string {
  return ENGINE_LABELS[engine] ?? engine
}

export function engineVendorLabel(engine: string): string {
  return ENGINE_VENDOR_LABELS[engine] ?? engine
}

/** Display label for an OpenRouter model slug (or legacy panel id). */
export function modelSlugLabel(slug: string): string {
  if (MODEL_SLUG_LABELS[slug]) return MODEL_SLUG_LABELS[slug]
  if (!slug.includes('/')) return engineLabel(slug)
  const tail = slug.split('/').pop() ?? slug
  return tail.replace(/-/g, ' ')
}
