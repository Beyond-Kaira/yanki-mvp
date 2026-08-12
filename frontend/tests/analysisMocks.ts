import { vi } from 'vitest'
import type { Analysis, AnalysisEnvelope } from '@/lib/contracts'
import type { FetchedAnalysisSlices } from '@/lib/analysis-bundle'

export function envelopeFrom(analysis: Analysis): AnalysisEnvelope {
  const { result: _result, ...envelope } = analysis
  return envelope
}

export function slicesFrom(analysis: Analysis): FetchedAnalysisSlices {
  const { result } = analysis
  return {
    kyc: { kyc: result.kyc },
    prompts: { prompts: result.prompts },
    geo: {
      responses: result.responses,
      geo_score: result.geo_score,
      footprint_count: result.footprint_count,
      total_responses: result.total_responses,
      reliability_score: result.reliability_score,
      interventions: result.interventions,
      citation_summary: result.citation_summary ?? null,
      geo_records: result.geo_records ?? [],
      engine_presence: result.engine_presence,
      competitors_appeared: result.competitors_appeared,
    },
    serp: result.serp,
    seo: result.seo,
  }
}

export function wireAnalysisPollMocks(
  mockedGet: ReturnType<typeof vi.fn>,
  mockedFetchSlices: ReturnType<typeof vi.fn>,
  analysis: Analysis,
) {
  mockedGet.mockResolvedValue(envelopeFrom(analysis))
  mockedFetchSlices.mockResolvedValue(slicesFrom(analysis))
}
