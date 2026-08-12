import type {
  Analysis,
  AnalysisEnvelope,
  AnalysisResult,
  KYC,
  Prompt,
  SerpVisibility,
  SeoAudit,
} from '@/lib/contracts'
import type { AnalysisResponse } from '@/lib/contracts'

/** Which slice routes to fetch after the thin poll envelope reaches a terminal state. */
export type AnalysisSliceMode = 'search' | 'ai' | 'full'

export type AnalysisKycSlice = { kyc: KYC | null }

export type AnalysisPromptsSlice = { prompts: Prompt[] }

export type AnalysisGeoSlice = {
  responses: AnalysisResponse[]
  geo_score: number | null
  footprint_count: number | null
  total_responses: number | null
  reliability_score?: number | null
  interventions?: AnalysisResult['interventions']
  citation_summary?: Record<string, unknown> | null
  geo_records: AnalysisResult['geo_records']
  engine_presence: AnalysisResult['engine_presence']
  competitors_appeared: AnalysisResult['competitors_appeared']
}

export type FetchedAnalysisSlices = {
  kyc?: AnalysisKycSlice
  prompts?: AnalysisPromptsSlice
  geo?: AnalysisGeoSlice
  serp?: SerpVisibility | null
  seo?: SeoAudit | null
}

export function emptyAnalysisResult(): AnalysisResult {
  return {
    kyc: null,
    prompts: [],
    responses: [],
    geo_score: null,
    footprint_count: null,
    total_responses: null,
    geo_records: [],
    engine_presence: null,
    competitors_appeared: null,
    serp: null,
    seo: null,
  }
}

/** Merge a thin envelope with optional slice payloads into the legacy ``Analysis`` shape. */
export function mergeAnalysis(
  envelope: AnalysisEnvelope,
  slices: FetchedAnalysisSlices = {},
): Analysis {
  const geo = slices.geo
  return {
    ...envelope,
    result: {
      kyc: slices.kyc?.kyc ?? null,
      prompts: slices.prompts?.prompts ?? [],
      responses: geo?.responses ?? [],
      geo_score: geo?.geo_score ?? envelope.geo_score ?? null,
      footprint_count: geo?.footprint_count ?? envelope.footprint_count ?? null,
      total_responses: geo?.total_responses ?? envelope.total_responses ?? null,
      reliability_score:
        geo?.reliability_score ?? envelope.reliability_score ?? null,
      interventions: geo?.interventions ?? null,
      citation_summary: geo?.citation_summary ?? null,
      geo_records: geo?.geo_records ?? [],
      engine_presence: geo?.engine_presence ?? null,
      competitors_appeared: geo?.competitors_appeared ?? null,
      serp: slices.serp ?? null,
      seo: slices.seo ?? null,
    },
  }
}

/** Poll placeholder: envelope fields for progress UI, empty result until slices load. */
export function analysisFromEnvelope(envelope: AnalysisEnvelope): Analysis {
  return mergeAnalysis(envelope, {})
}

export function slicePathsForMode(mode: AnalysisSliceMode): string[] {
  switch (mode) {
    case 'search':
      return ['serp', 'seo']
    case 'ai':
      return ['geo', 'kyc', 'prompts']
    case 'full':
      return ['geo', 'kyc', 'prompts', 'serp', 'seo']
  }
}
