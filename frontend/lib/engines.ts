// Panel engine identity in one place: which engines are on the panel, and what
// each is called on screen. Every surface that names an engine reads from here
// — the progress panel, both results screens, the answer table, and
// /methodology — so a name can never drift between two pages.

// Build-time import of the GENERATED artifact (scripts/gen_methodology.py, run
// by `make gen-types`), which carries the backend's DEFAULT_PANEL verbatim.
// Sourcing the ids here instead of retyping them keeps this module honest
// against the backend default without a second hand-kept list.
//
// Caveat: the artifact is a snapshot of the DEFAULT panel, not a deploy's
// effective one — `registry._panel_engines` still lets `PANEL_ENGINES` override
// it at runtime. Tracking that needs the effective panel on the API envelope.
import methodology from './checker_methodology.json'

export const PANEL_ENGINE_IDS: string[] = methodology.engines

// Short product names: what a reader recognizes. Used where space is tight and
// the vendor adds nothing — the run panel, score cards, answer tables.
const ENGINE_LABELS: Record<string, string> = {
  anthropic: 'Claude',
  openai: 'ChatGPT',
  gemini: 'Gemini',
  perplexity: 'Perplexity',
}

// Vendor-qualified names: used where the vendor IS the information, i.e. the
// methodology page explaining which companies' models answer the prompts.
const ENGINE_VENDOR_LABELS: Record<string, string> = {
  anthropic: 'Anthropic (Claude)',
  openai: 'OpenAI (GPT)',
  gemini: 'Google (Gemini)',
  perplexity: 'Perplexity',
}

// An id these maps have not been taught yet falls back to the raw value:
// showing `mistral` is honest, hiding the engine is not.
export function engineLabel(engine: string): string {
  return ENGINE_LABELS[engine] ?? engine
}

export function engineVendorLabel(engine: string): string {
  return ENGINE_VENDOR_LABELS[engine] ?? engine
}
