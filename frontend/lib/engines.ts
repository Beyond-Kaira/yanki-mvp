// Panel engine identity in one place: the ids the backend stamps on every
// response (backend/app/providers/registry.py DEFAULT_PANEL) and the product
// names readers actually recognize. The progress screen and the results screen
// both read from here so the two can never drift apart.

export const PANEL_ENGINE_IDS = ['anthropic', 'openai', 'gemini', 'perplexity']

const ENGINE_LABELS: Record<string, string> = {
  anthropic: 'Claude',
  openai: 'ChatGPT',
  gemini: 'Gemini',
  perplexity: 'Perplexity',
}

// An id this list has not been taught yet falls back to the raw value: showing
// `mistral` is honest, hiding the engine is not.
export function engineLabel(engine: string): string {
  return ENGINE_LABELS[engine] ?? engine
}
