import type { Analysis } from '@/lib/contracts'
import {
  groupByQuestion,
  runEngineIds,
  type QuestionGroup,
} from '@/lib/results'

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>
  }
  return null
}

function hostnameFromUrl(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

export function analysisDomain(analysis: Analysis): string {
  const company =
    analysis.result.kyc && typeof analysis.result.kyc.company === 'string'
      ? analysis.result.kyc.company
      : null
  return company || hostnameFromUrl(analysis.url)
}

export function humanizeKey(key: string): string {
  return key
    .split('_')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

// --- Prompts & Answers -------------------------------------------------------

export interface PromptsPageModel {
  domain: string
  analysisId: string
  groups: QuestionGroup[]
  engines: string[]
  geoPromptRows: GeoPromptRow[]
}

export interface GeoPromptRow {
  id: string
  prompt: string
  mentioned: boolean | null
  mentionContext: string | null
  answer: string | null
  sentiment: string | null
}

export function promptsFromAnalysis(analysis: Analysis): PromptsPageModel {
  const result = analysis.result
  const groups = groupByQuestion(result.prompts, result.responses)
  const engines = runEngineIds(result.responses, result.engine_presence)
  const geoPromptRows: GeoPromptRow[] = (result.geo_records ?? []).map((row) => ({
    id: row.id,
    prompt: row.prompt,
    mentioned: row.mentioned ?? null,
    mentionContext: row.mention_context ?? null,
    answer:
      row.grounded_answer?.trim() ||
      row.simulated_answer?.trim() ||
      row.answer_summary?.trim() ||
      null,
    sentiment: row.sentiment ?? null,
  }))

  return {
    domain: analysisDomain(analysis),
    analysisId: analysis.id,
    groups,
    engines,
    geoPromptRows,
  }
}

// --- Citations ---------------------------------------------------------------

export interface CitationUrlRow {
  url: string | null
  title: string | null
  mentionsBrand: boolean | null
  sourceType: string | null
}

export interface CitationDomainDetail {
  domain: string
  count: number
  urls: CitationUrlRow[]
}

export interface CitationSummaryMetrics {
  recordCount: number | null
  citeRate: number | null
  ownedRate: number | null
  earnedRate: number | null
  avgCitations: number | null
}

export interface CitationsPageModel {
  domain: string
  analysisId: string
  summary: CitationSummaryMetrics
  domains: CitationDomainDetail[]
}

function domainFromCitation(raw: unknown): string | null {
  const row = asRecord(raw)
  if (!row) return null
  const domain = row.source_domain ?? row.domain
  if (typeof domain === 'string' && domain.trim()) {
    return domain.trim().toLowerCase().replace(/^www\./, '')
  }
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

function citationUrlRow(raw: unknown): CitationUrlRow {
  const row = asRecord(raw)
  if (!row) {
    return { url: null, title: null, mentionsBrand: null, sourceType: null }
  }
  return {
    url: typeof row.url === 'string' ? row.url : null,
    title:
      (typeof row.source_title === 'string' && row.source_title) ||
      (typeof row.title === 'string' && row.title) ||
      null,
    mentionsBrand:
      typeof row.mentions_target_brand === 'boolean'
        ? row.mentions_target_brand
        : null,
    sourceType:
      (typeof row.source_type === 'string' && row.source_type) ||
      (typeof row.type === 'string' && row.type) ||
      null,
  }
}

function collectCitationDomains(analysis: Analysis): CitationDomainDetail[] {
  const buckets = new Map<string, CitationDomainDetail>()

  function add(raw: unknown) {
    const domain = domainFromCitation(raw)
    if (!domain) return
    const urlRow = citationUrlRow(raw)
    const existing = buckets.get(domain)
    if (existing) {
      existing.count += 1
      if (
        urlRow.url &&
        !existing.urls.some((item) => item.url === urlRow.url)
      ) {
        existing.urls.push(urlRow)
      }
      return
    }
    buckets.set(domain, {
      domain,
      count: 1,
      urls: urlRow.url || urlRow.title ? [urlRow] : [],
    })
  }

  for (const record of analysis.result.geo_records ?? []) {
    if (!Array.isArray(record.citations)) continue
    for (const item of record.citations) add(item)
  }

  // Fallback when geo_records have no citation arrays yet.
  if (buckets.size === 0) {
    for (const response of analysis.result.responses) {
      const audit = asRecord((response as { audit?: unknown }).audit ?? null)
      const citations = audit?.citations
      if (!Array.isArray(citations)) continue
      for (const item of citations) add(item)
    }
  }

  return [...buckets.values()].sort((a, b) => b.count - a.count)
}

function readSummaryMetrics(analysis: Analysis): CitationSummaryMetrics {
  const raw = asRecord(
    (analysis.result as { citation_summary?: unknown }).citation_summary ?? null,
  )
  const num = (key: string): number | null => {
    const value = raw?.[key]
    return typeof value === 'number' && Number.isFinite(value) ? value : null
  }
  return {
    recordCount: num('record_count'),
    citeRate: num('cite_rate'),
    ownedRate: num('owned_rate'),
    earnedRate: num('earned_rate'),
    avgCitations: num('avg_citations'),
  }
}

export function citationsFromAnalysis(analysis: Analysis): CitationsPageModel {
  return {
    domain: analysisDomain(analysis),
    analysisId: analysis.id,
    summary: readSummaryMetrics(analysis),
    domains: collectCitationDomains(analysis),
  }
}

// --- Drivers & Gaps ----------------------------------------------------------

export interface ClaimBucket {
  category: string
  label: string
  claims: string[]
}

export interface InterventionDetail {
  id: string
  title: string
  description: string | null
  label: string | null
  priority: number | null
}

export interface DriversPageModel {
  domain: string
  analysisId: string
  drivers: ClaimBucket[]
  gaps: ClaimBucket[]
  interventions: InterventionDetail[]
}

function collectCategoryClaims(
  analysis: Analysis,
  field: 'visibility_drivers' | 'visibility_gaps',
): ClaimBucket[] {
  const byCategory = new Map<string, Set<string>>()

  for (const record of analysis.result.geo_records ?? []) {
    const block = asRecord(record[field] ?? null)
    if (!block) continue
    for (const [category, value] of Object.entries(block)) {
      if (!Array.isArray(value)) continue
      let set = byCategory.get(category)
      if (!set) {
        set = new Set()
        byCategory.set(category, set)
      }
      for (const claim of value) {
        if (typeof claim === 'string' && claim.trim()) set.add(claim.trim())
      }
    }
  }

  return [...byCategory.entries()]
    .map(([category, claims]) => ({
      category,
      label: humanizeKey(category),
      claims: [...claims],
    }))
    .filter((bucket) => bucket.claims.length > 0)
    .sort((a, b) => b.claims.length - a.claims.length)
}

function collectInterventionDetails(analysis: Analysis): InterventionDetail[] {
  const raw = (analysis.result as { interventions?: unknown }).interventions
  if (!Array.isArray(raw)) return []
  const rows: InterventionDetail[] = []
  for (const [index, item] of raw.entries()) {
    const rec = asRecord(item)
    if (!rec) continue
    const title =
      (typeof rec.title === 'string' && rec.title) ||
      (typeof rec.name === 'string' && rec.name) ||
      (typeof rec.label === 'string' && rec.label) ||
      null
    if (!title) continue
    rows.push({
      id:
        (typeof rec.id === 'string' && rec.id) ||
        `${title}-${index}`,
      title,
      description:
        typeof rec.description === 'string' ? rec.description : null,
      label: typeof rec.label === 'string' ? rec.label : null,
      priority:
        typeof rec.priority_score === 'number' ? rec.priority_score : null,
    })
  }
  return rows
}

export function driversFromAnalysis(analysis: Analysis): DriversPageModel {
  return {
    domain: analysisDomain(analysis),
    analysisId: analysis.id,
    drivers: collectCategoryClaims(analysis, 'visibility_drivers'),
    gaps: collectCategoryClaims(analysis, 'visibility_gaps'),
    interventions: collectInterventionDetails(analysis),
  }
}

export const LAST_ANALYSIS_STORAGE_KEY = 'yanki:lastAnalysisId'

export function rememberAnalysisId(id: string): void {
  try {
    sessionStorage.setItem(LAST_ANALYSIS_STORAGE_KEY, id)
  } catch {
    // ignore quota / private mode
  }
}

export function readRememberedAnalysisId(): string | null {
  try {
    return sessionStorage.getItem(LAST_ANALYSIS_STORAGE_KEY)
  } catch {
    return null
  }
}
