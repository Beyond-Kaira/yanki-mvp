// Shapes for the visibility insights modules, mirroring the `InsightsOut`
// envelope in docs/superpowers/specs/2026-08-04-visibility-insights-design.md.
//
// These live here rather than in contracts.ts so the preview screen and the
// real API envelope can share one component-facing shape.

// Every count on the screen is a number of ANSWERS, never a number of string
// occurrences. One answer repeating a brand ten times must not outweigh ten
// answers naming it once.

export type Ownership = 'ours' | 'shared' | 'competitor' | 'unclaimed'
export type Tier = 'core' | 'secondary' | 'none'
export type Presence = 'present' | 'high-impact-missing' | 'missing'

// The three intent groups the engine grid collapses the six categories into,
// so a cell is backed by enough answers to be worth reading. See §1.2 of the
// design: with the categories kept apart, a cell is two answers and can only
// ever read 0/2, 1/2 or 2/2.
export const INTENT_GROUPS = ['discovery', 'comparison', 'recommendation'] as const
export type IntentGroup = (typeof INTENT_GROUPS)[number]

export const GROUP_CATEGORIES: Record<IntentGroup, string[]> = {
  discovery: ['makers', 'best-of'],
  comparison: ['comparison', 'alternatives'],
  recommendation: ['recommendation', 'use-case'],
}

export interface Ratio {
  mentioned: number
  total: number
}

export interface IntentGroupStat extends Ratio {
  group: IntentGroup
}

export interface CompetitorMention {
  name: string
  answers: number
}

export interface EngineInsight extends Ratio {
  engine: string
  groups: IntentGroupStat[]
  // Answers from this engine that named the brand, and the per-competitor
  // answer counts they compete with. `share` is brand / (brand + competitors),
  // null when the engine produced neither.
  brandAnswers: number
  competitors: CompetitorMention[]
  share: number | null
  // Of the `mentioned` answers (those that named the brand at all), how many
  // named it BEFORE any competitor — i.e. the brand was the first brand name
  // to appear. A ratio out of `mentioned`, not out of `total`: an engine that
  // never named the brand has nothing to rank, and renders "not named" rather
  // than a 0 that would read as "always named last".
  firstMentions: number
}

export interface CategoryGap {
  category: string
  total: number
  // Answers naming at least one competitor while leaving the brand out.
  lost: number
  competitors: string[]
}

export interface VisibilityGap {
  answersLost: number
  total: number
  categories: CategoryGap[]
}

export interface EntityStat {
  name: string
  // In how many scored answers the entity appears.
  answers: number
  ownership: Ownership
  tier: Tier
  // Only set for entities that came from the KYC profile.
  presence?: Presence
}

export interface EntityCoverage {
  present: number
  total: number
  entities: EntityStat[]
}

export interface EntityLandscape {
  coreThreshold: number
  entities: EntityStat[]
}

export interface DriverStat extends Ratio {
  category: string
  // Share of ALL the brand's mentions that came from this category; the six
  // sum to 1, and every one is 0 when the brand was never named.
  contribution: number
}

export interface Insights {
  brand: string
  subject: string
  promptSet: string
  scoredAnswers: number
  // Brand-probe answers, withheld from every module above because their prompt
  // names the company inside the question. Null when the run had no probes —
  // the checker's fixed set never plants the brand.
  probe: Ratio | null
  engines: EngineInsight[]
  gap: VisibilityGap
  entityCoverage: EntityCoverage
  entityLandscape: EntityLandscape
  drivers: DriverStat[]
}

export function percent(mentioned: number, total: number): number {
  return total > 0 ? Math.round((mentioned / total) * 100) : 0
}
