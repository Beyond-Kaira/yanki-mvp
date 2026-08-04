import type { Analysis } from '@/lib/contracts'

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

function hostnameFromUrl(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>
  }
  return null
}

function domainFromCitation(raw: unknown): string | null {
  const row = asRecord(raw)
  if (!row) return null
  const domain = row.source_domain ?? row.domain
  if (typeof domain === 'string' && domain.trim()) return domain.trim().toLowerCase()
  const url = row.url
  if (typeof url === 'string') {
    try {
      return new URL(url).hostname.replace(/^www\./, '')
    } catch {
      return null
    }
  }
  return null
}

function collectCitations(analysis: Analysis): CitationDomainRow[] {
  const counts = new Map<string, number>()
  for (const response of analysis.result.responses) {
    const audit = asRecord(
      (response as { audit?: unknown }).audit ?? null,
    )
    const citations = audit?.citations
    if (!Array.isArray(citations)) continue
    for (const item of citations) {
      const domain = domainFromCitation(item)
      if (!domain) continue
      counts.set(domain, (counts.get(domain) ?? 0) + 1)
    }
  }
  return [...counts.entries()]
    .map(([domain, count]) => ({ domain, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 8)
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
  const total = result.total_responses ?? result.responses.length
  const hits = result.footprint_count ?? result.responses.filter((r) => r.footprint).length
  const citeRate = total > 0 ? hits / total : null
  const reliability = (result as { reliability_score?: number | null }).reliability_score
  const citations = collectCitations(analysis)
  const interventions = collectInterventions(analysis)
  const company =
    result.kyc && typeof result.kyc.company === 'string' ? result.kyc.company : null

  return {
    domain: company || hostnameFromUrl(analysis.url),
    geoScore: normalizeGeoScore(result.geo_score),
    citeRate,
    reliability: typeof reliability === 'number' ? reliability : null,
    citations,
    interventions,
    isSample: false,
    analysisId: analysis.id,
  }
}
