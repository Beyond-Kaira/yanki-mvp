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

// Accounts (PR #9). Login answers with the user plus a bearer token while
// setting the refresh cookie. Re-exported here rather than restated in
// `lib/auth.ts` so a schema change reaches the auth screens through the
// generated types.
// `/auth/me` returns CurrentUserOut — the identity fields PLUS the org, the
// caller's role in it, and the permission list. Login and signup still return
// the narrow UserOut, so the org-dependent fields are optional here and the
// shell renders without them until /me resolves.
export type AuthUser = Schemas['UserOut'] &
  Partial<Omit<Schemas['CurrentUserOut'], keyof Schemas['UserOut']>>

export type Organization = Schemas['OrganizationOut']

// One organization the signed-in user belongs to, with their role in it. The
// multi-org list on `/auth/me`; the singular `organization` on AuthUser is the
// one currently being acted in, this is the full set the switcher offers.
export type OrganizationMembership = Schemas['OrganizationMembershipOut']

// --- Sessions / devices ----------------------------------------------------
//
// `AuthSession` is one active sign-in (a device/login) as its owner sees it. It
// carries NO token and no replayable material — `id` is a family id that names a
// session for revocation only. See backend/app/api/auth_routes.py.

export type AuthSession = Schemas['AuthSessionOut']

export type AuthSessionList = Schemas['AuthSessionListOut']

export type SessionRevokeAllResult = Schemas['SessionRevokeAllOut']

export type Credentials = Schemas['LoginRequest']

// Sign-up carries its own schema even though it is {email, password} today, so
// each call site is typed against the endpoint it actually posts to. They are
// already not interchangeable — `SignupRequest.password` is min_length 8 where
// `LoginRequest.password` is 1 — and the day sign-up gains a field, one of these
// changes and the other does not. Sharing a type would keep TypeScript quiet
// through exactly the change it is here to catch.
// The generated type is stricter than the wire contract. openapi-typescript
// marks a property with a DEFAULT as required, but `openapi.json` lists only
// `email` and `password` in `required` — the backend genuinely accepts a body
// without an account type and treats it as an individual, which is what keeps
// an older client working. Corrected here rather than by making every caller
// pass a value it does not care about.
type SignupWire = Schemas['SignupRequest']
export type SignupCredentials = Pick<SignupWire, 'email' | 'password'> &
  Partial<Pick<SignupWire, 'account_type' | 'organization_name'>>

export type LoginResponse = Schemas['LoginResponse']

// Independent Site Audit projects. These aliases stay deliberately thin: the
// backend OpenAPI schema is the source of truth for every field rendered by the
// project dashboard.
export type SeoProject = Schemas['SeoProjectOut']

export type SeoProjectDetail = Schemas['SeoProjectDetailOut']

export type SiteAuditRunSummary = Schemas['SiteAuditSummaryOut']

export type SiteAuditDetail = Schemas['SiteAuditDetailOut']

export type SiteAuditPage = Schemas['SiteAuditPageOut']

export type SiteAuditIssue = Schemas['SiteAuditIssueOut']

export type SiteAuditSchema = Schemas['SiteAuditSchemaOut']

export type CreateSeoProjectInput = Schemas['CreateSeoProjectRequest']

// --- Administration -------------------------------------------------------

export type AdminMember = Schemas['AdminMemberOut']

export type AdminMemberList = Schemas['AdminUserListOut']

export type AdminOrganization = Schemas['AdminOrganizationOut']

export type AdminInvitation = Schemas['AdminInvitationOut']

export type AdminInvitationList = Schemas['AdminInvitationListOut']

// The create/resend response — the only shape in the API that carries an
// invitation token, and only in `accept_url`. Nothing persists it client-side.
export type AdminInvitationCreated = Schemas['AdminInvitationCreatedOut']

// The public accept flow. The preview is what an invited person sees before
// they commit; the accept response is an ordinary login response, so the invitee
// lands signed in rather than at a login form.
export type InvitationPreview = Schemas['InvitationPreviewOut']

// --- Audit log ------------------------------------------------------------

export type AuditEvent = Schemas['AuditEventOut']

export type AuditEventList = Schemas['AuditEventListOut']

export type AuditIntegrity = Schemas['AuditIntegrityOut']

// --- Backlink Intelligence (P8.3) -----------------------------------------
//
// The module ships behind BACKLINKS_ENABLED, so in most workspaces these
// endpoints answer 404 and the UI renders a "not enabled" state rather than an
// error. See `useBacklinkProfile` for how the two 404s are told apart.
//
// Nullable numbers here mean NOT MEASURED, never zero: an authority or
// toxicity score of `null` renders as "—". Collapsing that to 0 would state a
// confident number the backend deliberately declined to state.

export type BacklinkSummary = Schemas['BacklinkSummaryOut']

export type BacklinkImportSummary = Schemas['BacklinkImportOut']

export type Backlink = Schemas['BacklinkOut']

export type BacklinkPage = Schemas['BacklinkPageOut']

export type ReferringDomain = Schemas['ReferringDomainOut']

export type ReferringDomainPage = Schemas['ReferringDomainPageOut']

export type AnchorDistribution = Schemas['AnchorDistributionOut']

export type VelocityPoint = Schemas['VelocityPointOut']

export type LinkEvent = Schemas['LinkEventOut']

export type LinkEventPage = Schemas['LinkEventPageOut']

export type BacklinkOpportunities = Schemas['OpportunitiesOut']

export type LinkGapRow = Schemas['GapRowOut']

export type UnlinkedMention = Schemas['UnlinkedMentionOut']

export type BacklinkRefreshResult = Schemas['RefreshOut']

// The toxicity reasons ride along with every flagged domain as a free-form
// list; this is the shape the backend actually emits for each one. Typed here
// rather than inline so the panel that renders the evidence cannot drift from
// the panel that renders the band.
export interface ToxicityReason {
  code: string
  label: string
  weight: number
  evidence: string
}

export type ToxicityBand = 'low' | 'medium' | 'high'

export type LinkEventKind = 'new' | 'lost' | 'regained' | 'changed'
