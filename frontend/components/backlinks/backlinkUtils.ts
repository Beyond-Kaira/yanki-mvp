import type { ToxicityBand, ToxicityReason } from '@/lib/contracts'

/** "Not measured" is not zero.
 *
 * The backend is careful to send `null` for a score it declined to compute, and
 * the whole point of that care is lost if the UI renders it as `0` — a zero is
 * a confident claim about a profile, and a dash is an honest absence. Every
 * nullable number from this module goes through here.
 */
export function formatMetric(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : String(value)
}

export function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return value.toLocaleString('en-US')
}

export function formatPercent(share: number | null | undefined): string {
  if (share === null || share === undefined) return '—'
  return `${(share * 100).toFixed(1)}%`
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return '—'
  return parsed.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

export const TOXICITY_TONE: Record<ToxicityBand, string> = {
  low: 'bg-success-soft text-success-strong',
  medium: 'bg-warning-soft text-warning-strong',
  high: 'bg-danger-soft text-danger-strong',
}

export const EVENT_TONE: Record<string, string> = {
  new: 'bg-success-soft text-success-strong',
  lost: 'bg-danger-soft text-danger-strong',
  regained: 'bg-primary-soft text-primary-strong',
  changed: 'bg-warning-soft text-warning-strong',
}

export const ANCHOR_CLASS_LABELS: Record<string, string> = {
  exact: 'Exact match',
  partial: 'Partial match',
  brand: 'Brand',
  naked: 'Naked URL',
  generic: 'Generic',
}

export function bandOf(value: string | null | undefined): ToxicityBand {
  return value === 'high' || value === 'medium' ? value : 'low'
}

/** The reasons list arrives as free-form JSON; read it defensively.
 *
 * A toxicity band without its reasons must never render — the backend has a
 * test that refuses to emit one — so anything unreadable here is dropped rather
 * than shown as an unexplained flag.
 */
export function readReasons(raw: unknown): ToxicityReason[] {
  if (!Array.isArray(raw)) return []
  return raw.flatMap((entry) => {
    if (typeof entry !== 'object' || entry === null) return []
    const record = entry as Record<string, unknown>
    const label = typeof record.label === 'string' ? record.label : null
    if (!label) return []
    return [
      {
        code: typeof record.code === 'string' ? record.code : '',
        label,
        weight: typeof record.weight === 'number' ? record.weight : 0,
        evidence: typeof record.evidence === 'string' ? record.evidence : '',
      },
    ]
  })
}

export interface AuthorityTerm {
  key: string
  label: string
  points: number
  weight: number
  explains: string
}

/** The authority decomposition, ready to render.
 *
 * Published rather than summarized: the score's entire claim is that it is
 * decomposable and that the terms SUM to the number shown. So every term the
 * backend sent is rendered, each with the sentence it sent explaining itself —
 * a score that shows only its total is the thing the methodology page exists to
 * avoid being.
 *
 * `caveats` is read separately (it is a list of sentences, not a term) and is
 * every bit as load-bearing: it is where "this is not PageRank" lives.
 */
export function readAuthorityComponents(raw: unknown): AuthorityTerm[] {
  if (typeof raw !== 'object' || raw === null) return []
  return Object.entries(raw as Record<string, unknown>).flatMap(([key, value]) => {
    if (typeof value !== 'object' || value === null || Array.isArray(value)) return []
    const record = value as Record<string, unknown>
    if (typeof record.points !== 'number') return []
    return [
      {
        key,
        label: humanize(key),
        points: record.points,
        weight: typeof record.weight === 'number' ? record.weight : 0,
        explains: typeof record.explains === 'string' ? record.explains : '',
      },
    ]
  })
}

export function readAuthorityCaveats(raw: unknown): string[] {
  if (typeof raw !== 'object' || raw === null) return []
  const caveats = (raw as Record<string, unknown>).caveats
  if (!Array.isArray(caveats)) return []
  return caveats.filter((entry): entry is string => typeof entry === 'string')
}

function humanize(key: string): string {
  const spaced = key.replace(/_/g, ' ')
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}
