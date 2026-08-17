import { describe, expect, it } from 'vitest'
import {
  analysisRouteUsesSession,
  resolveBoundAnalysisId,
} from '@/lib/analysis-route'

describe('analysis route binding', () => {
  it('treats overview pages as fresh starts without a query param', () => {
    expect(analysisRouteUsesSession('/ai-visibility')).toBe(false)
    expect(analysisRouteUsesSession('/search-visibility')).toBe(false)
  })

  it('binds subpages to the remembered run when the URL has no param', () => {
    expect(analysisRouteUsesSession('/ai-visibility/prompts')).toBe(true)
    expect(analysisRouteUsesSession('/search-visibility/keywords')).toBe(true)
  })

  it('prefers the query param over session memory', () => {
    expect(
      resolveBoundAnalysisId('from-url', '/ai-visibility/prompts', 'from-session'),
    ).toBe('from-url')
  })

  it('falls back to session on subpages only', () => {
    expect(
      resolveBoundAnalysisId(null, '/ai-visibility/prompts', 'remembered'),
    ).toBe('remembered')
    expect(
      resolveBoundAnalysisId(null, '/ai-visibility', 'remembered'),
    ).toBeNull()
  })
})
