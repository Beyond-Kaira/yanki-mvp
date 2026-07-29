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

export type AnalysisResult = Omit<Schemas['ResultOut'], 'kyc'> & {
  kyc: KYC | null
  reliability_score?: number | null
  interventions?: Array<Record<string, unknown>> | Record<string, unknown> | null
}

export type Analysis = Omit<
  Schemas['AnalysisOut'],
  'status' | 'current_step' | 'result'
> & {
  status: AnalysisStatus
  current_step: PipelineStep | null
  result: AnalysisResult
}
