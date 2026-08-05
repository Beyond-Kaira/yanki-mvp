import type { Analysis } from '@/lib/contracts'
import { citationsFromAnalysis } from '@/lib/ai-visibility-data'

export interface CitationDomainRow {
  domain: string
  count: number
}

export interface InterventionRow {
  title: string
}

export interface AiOverviewModel {
  domain: string
  geoScore: number | null
  citeRate: number | null
  reliability: number | null
  citations: CitationDomainRow[]
  interventions: InterventionRow[]
  isSample: boolean
  analysisId: string | null
}

const SAMPLE: AiOverviewModel = {
  domain: 'trendyol.com',
  geoScore: 42,
  citeRate: 0.18,
  reliability: 0.77,
  citations: [
    { domain: 'f6s.com', count: 23 },
    { domain: 'reddit.com', count: 17 },
    { domain: 'medium.com', count: 14 },
    { domain: 'linkedin.com', count: 12 },
    { domain: 'wikipedia.org', count: 9 },
    { domain: 'finance.yahoo.com', count: 8 },
  ],
  interventions: [
    { title: 'Strengthen brand mentions on high-authority sources' },
    { title: 'Create in-depth content for top-cited topics' },
    { title: 'Improve entity consistency across owned pages' },
    { title: 'Earn citations from comparison roundups' },
    { title: 'Build topical authority around category prompts' },
  ],
  isSample: true,
  analysisId: null,
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>
  }
  return null
}

function collectInterventions(analysis: Analysis): InterventionRow[] {
  const raw = (analysis.result as { interventions?: unknown }).interventions
  if (!Array.isArray(raw)) return []
  const rows: InterventionRow[] = []
  for (const item of raw) {
    const rec = asRecord(item)
    if (!rec) continue
    const title =
      (typeof rec.title === 'string' && rec.title) ||
      (typeof rec.name === 'string' && rec.name) ||
      (typeof rec.label === 'string' && rec.label) ||
      null
    if (title) rows.push({ title })
  }
  return rows.slice(0, 6)
}

function normalizeGeoScore(score: number | null | undefined): number | null {
  if (score == null || Number.isNaN(score)) return null
  // Legacy mention-rate fraction vs composite 0–100.
  if (score >= 0 && score <= 1) return Math.round(score * 100)
  return Math.round(Math.max(0, Math.min(100, score)))
}

export function sampleOverview(): AiOverviewModel {
  return SAMPLE
}

export function overviewFromAnalysis(analysis: Analysis): AiOverviewModel {
  const result = analysis.result
  const citationsPage = citationsFromAnalysis(analysis)
  const total = result.total_responses ?? result.responses.length
  const hits =
    result.footprint_count ??
    result.responses.filter((response) => response.footprint).length
  // Prefer measured citation_summary cite_rate when present.
  const citeRate =
    citationsPage.summary.citeRate ?? (total > 0 ? hits / total : null)
  const reliability = (result as { reliability_score?: number | null })
    .reliability_score

  return {
    domain: citationsPage.domain,
    geoScore: normalizeGeoScore(result.geo_score),
    citeRate,
    reliability: typeof reliability === 'number' ? reliability : null,
    citations: citationsPage.domains.slice(0, 8).map(({ domain, count }) => ({
      domain,
      count,
    })),
    interventions: collectInterventions(analysis),
    isSample: false,
    analysisId: analysis.id,
  }
}
