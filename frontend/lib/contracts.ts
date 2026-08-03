// Friendly, hand-named types for the app to import.
//
// `lib/types.ts` is GENERATED from the backend OpenAPI schema by `make gen-types`
// (do not hand-edit it). This module is the stable, hand-maintained seam over it:
// it re-exports the generated component schemas under the names the rest of the
// codebase uses, and narrows the few fields the schema can only express as plain
// strings / free-form objects (status, current_step, kyc) to their locked SPEC
// shapes. Import app types from here, never from `./types`.

import type { components } from './types'

type Schemas = components['schemas']

// The backend serializes these as plain strings; narrow to the locked SPEC values.
export type AnalysisStatus = 'queued' | 'running' | 'done' | 'failed'

export type PipelineStep =
  | 'discovery'
  | 'kyc'
  | 'prompts'
  | 'execute'
  | 'footprint'
  | 'scoring'

// KYC is stored/serialized as a free-form JSON object; this is its locked shape.
export interface KYC {
  company: string
  description: string
  industry: string
  aliases: string[]
  products: string[]
  services: string[]
  keywords: string[]
  locations: string[]
  competitors: string[]
  // Added with the pipeline quality pass (docs/pipeline-quality-plan.md, K1):
  // the buying category and the use cases prompt generation is built from.
  // Optional because analyses run before that change have no such key in their
  // stored JSON — KycCard already coerces every field defensively.
  category?: string
  use_cases?: string[]
}

export type Prompt = Schemas['PromptOut']

export type AnalysisResponse = Schemas['ResponseOut']

export type CreateAnalysisResponse = Schemas['CreateAnalysisResponse']

// Public checker (P5.4). The submit returns both the analysis id (polled via the
// shared getAnalysis) and a submission_id carried to the results route for
// P5.5's email gate. EnginePresence / CompetitorMention are the read-time
// checker aggregates that ride on the shared result envelope.
export type CheckerSubmitResponse = Schemas['CheckerSubmitResponse']

// Public product-updates waitlist (P5.13). The backend records + normalizes the
// email and returns a simple ok envelope; the request carries only the email.
export type WaitlistSignupResponse = Schemas['WaitlistResponse']

export type EnginePresence = Schemas['EnginePresence']

export type CompetitorMention = Schemas['CompetitorMention']

// SERP visibility (ADR-28) — whether the brand also shows up in ordinary search
// results, read from an open-source metasearch instance. `AnalysisResult.serp`
// is null on every run that did not measure it, and `serp.score` is separately
// null on a run that measured and could not read the results: "we did not look"
// and "we looked and could not see" are both distinct from a zero.
export type SerpVisibility = Schemas['SerpVisibilityOut']

export type SerpCheck = Schemas['SerpCheckOut']

// SEO / AI-readiness audit (ADR-31) — why an answer engine can or cannot read
// the site, computed from the crawl discovery already performed. `AnalysisResult.seo`
// is null on every run that did not audit (e.g. checker submissions — no site to
// look at). Within a present audit, `seo.grade`/`seo.score` are separately null on
// a run that produced no scorable checks. The grade is the headline, capped by
// critical failures so a fatal problem can't be averaged away.
export type SeoAudit = Schemas['SeoAuditOut']

export type SeoCheck = Schemas['SeoCheckOut']

export type AnalysisResult = Omit<Schemas['ResultOut'], 'kyc'> & {
  kyc: KYC | null
}

export type Analysis = Omit<
  Schemas['AnalysisOut'],
  'status' | 'current_step' | 'result'
> & {
  status: AnalysisStatus
  current_step: PipelineStep | null
  result: AnalysisResult
}
