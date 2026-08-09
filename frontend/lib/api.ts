import type {
  AdminInvitation,
  AdminInvitationCreated,
  AdminInvitationList,
  AdminMember,
  AdminMemberList,
  AdminOrganization,
  Analysis,
  AnalysisList,
  AuditEventList,
  AuditIntegrity,
  AuthSessionList,
  BacklinkOpportunities,
  BacklinkPage,
  BacklinkRefreshResult,
  BacklinkSummary,
  CheckerSubmitResponse,
  CreateAnalysisResponse,
    CreateSeoProjectInput,
  InvitationPreview,
  LinkEventPage,
  LoginResponse,
  ReferringDomainPage,
    SeoProject,
    SeoProjectDetail,
  SessionRevokeAllResult,
    SiteAuditDetail,
  WaitlistSignupResponse,
} from './contracts'
import { getActiveOrgId } from './active-org'
import { getAccessToken, refreshAccessToken } from './session'

// Thin fetch wrapper. All paths are relative — Next rewrites proxy them to the
// backend (see next.config.ts), so there is no CORS and no base URL to configure.

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

// Exported so `lib/auth.ts` surfaces backend failures the same way as the rest
// of the app instead of keeping a second copy of this shape handling.
export async function readErrorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json()
    // FastAPI/Pydantic validation errors: { detail: [{ msg }] } or { detail: "…" }.
    if (typeof body?.detail === 'string') return body.detail
    if (Array.isArray(body?.detail) && typeof body.detail[0]?.msg === 'string') {
      return body.detail[0].msg
    }
  } catch {
    // No JSON body — fall through to a generic message.
  }
  return `Request failed (${res.status}).`
}

function withBearer(init: RequestInit, token: string): RequestInit {
  const headers = new Headers(init.headers)
  headers.set('Authorization', `Bearer ${token}`)
  return { ...init, headers, credentials: 'same-origin' }
}

// Fold in the active organization as `X-Org-Id`, the header the backend already
// honours for org scoping. Applied once here — the single seam every authorized
// request passes through — rather than at each call site, so the switcher only
// has to set the stored org and every request follows. A caller that set the
// header itself wins, and a single-org user (no stored org) adds nothing.
function withActiveOrg(init: RequestInit): RequestInit {
  const orgId = getActiveOrgId()
  if (!orgId) return init
  const headers = new Headers(init.headers)
  if (!headers.has('X-Org-Id')) headers.set('X-Org-Id', orgId)
  return { ...init, headers }
}

// A request that needs the signed-in user. Access tokens are short-lived by
// design, so a 401 is the expected way to learn one has expired rather than an
// error to surface: rotate the refresh cookie once and replay the request.
//
// Once only. A second 401 after a fresh token means the session is genuinely
// over, and retrying past that is how a refresh loop starts.
export async function authorizedFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  // Scope is resolved before the bearer so the retry after a refresh carries the
  // same X-Org-Id as the first attempt.
  const scoped = withActiveOrg(init)
  const token = getAccessToken()
  const res = token
    ? await fetch(path, withBearer(scoped, token))
    : await fetch(path, { ...scoped, credentials: 'same-origin' })

  if (res.status !== 401) return res

  const refreshed = await refreshAccessToken()
  if (!refreshed) return res

  return fetch(path, withBearer(scoped, refreshed))
}

// Submitting an analysis is an authorized, metered action (ADR-45). It used to
// be a bare `fetch` against an open endpoint, which is why every run a customer
// started was attributed to nobody: the form sat behind sign-in while the
// request it sent carried no credential.
//
// The 429 needs care. Two different limits answer with it and they mean
// opposite things to the person reading the message — one is "you are going too
// fast, wait", the other is "you are out for the month, upgrade". The backend
// keeps them distinct (the plan refusal carries a `limit` field); collapsing
// them into "too many requests" would tell a customer to wait for something
// that will not change until next month.
export async function createAnalysis(url: string): Promise<CreateAnalysisResponse> {
  let res: Response
  try {
    res = await authorizedFetch('/api/v1/analyses', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    })
  } catch {
    throw new ApiError(
      "We couldn't reach the server. Check your connection and try again.",
      0,
    )
  }

  if (!res.ok) {
    let message: string
    if (res.status === 422) {
      message = "That doesn't look like a valid URL. Use http:// or https://."
    } else if (res.status === 401) {
      message = 'Your session has expired. Sign in again to run an analysis.'
    } else if (res.status === 403) {
      message = 'Your role cannot start an analysis. Ask an Analyst or above.'
    } else if (res.status === 503) {
      message = 'Analyses are unavailable on this deployment right now.'
    } else if (res.status === 429) {
      const detail = await readErrorMessage(res)
      message =
        detail === 'rate limit exceeded'
          ? 'You have started several analyses in a short time. Try again shortly.'
          : detail
    } else {
      message = await readErrorMessage(res)
    }
    throw new ApiError(message, res.status)
  }
  return (await res.json()) as CreateAnalysisResponse
}

export async function createCheckerAnalysis(
  brand: string,
  category: string,
): Promise<CheckerSubmitResponse> {
  // lang is intentionally omitted — the backend defaults it to 'en' (EN-only).
  const res = await fetch('/api/v1/checker', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ brand, category }),
  })
  if (!res.ok) {
    const message =
      res.status === 422
        ? 'Enter a brand and a category to check.'
        : await readErrorMessage(res)
    throw new ApiError(message, res.status)
  }
  return (await res.json()) as CheckerSubmitResponse
}

export async function submitLead(
  submissionId: string,
  email: string,
): Promise<void> {
  // The email gate (P5.5). The backend attaches the email to this one submission
  // row (append-only — a second lead on the same cached analysis never
  // overwrites another submission's email). 202 on success; body is ignored.
  const res = await fetch('/api/v1/checker/leads', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ submission_id: submissionId, email }),
  })
  if (!res.ok) {
    const message =
      res.status === 422
        ? 'Enter a valid email address.'
        : res.status === 404
          ? "We couldn't find that check to unlock."
          : await readErrorMessage(res)
    throw new ApiError(message, res.status)
  }
}

export async function joinWaitlist(
  email: string,
): Promise<WaitlistSignupResponse> {
  // Product-updates waitlist (P5.13). The email is validated + normalized
  // server-side; a malformed address is a 422 before any row is written. 202 on
  // success with an { ok: true } envelope.
  const res = await fetch('/api/v1/waitlist', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  })
  if (!res.ok) {
    const message =
      res.status === 422
        ? 'Enter a valid email address.'
        : await readErrorMessage(res)
    throw new ApiError(message, res.status)
  }
  return (await res.json()) as WaitlistSignupResponse
}

// Reading an analysis stays open to anonymous callers — a run with no
// organization is a capability URL, which is what every checker result and
// every pre-P7.6 row is. But a run that belongs to an organization is only
// served to that organization, so the poll has to carry the caller's bearer or
// the person who just started the analysis would be 404'd from their own
// result. `authorizedFetch` sends nothing extra when nobody is signed in, so
// the anonymous path is unchanged.
export async function getAnalysis(id: string): Promise<Analysis> {
  const res = await authorizedFetch(`/api/v1/analyses/${encodeURIComponent(id)}`, {
    headers: { Accept: 'application/json' },
    cache: 'no-store',
  })
  if (!res.ok) {
    // 422 = the path id is not a valid UUID (malformed URL). Treat it like 404
    // so the user sees the friendly not-found copy, not a raw Pydantic string.
    const message =
      res.status === 404 || res.status === 422
        ? "We couldn't find that analysis."
        : await readErrorMessage(res)
    throw new ApiError(message, res.status)
  }
  return (await res.json()) as Analysis
}

export interface AnalysisHistoryQuery {
  status?: string
  limit?: number
  offset?: number
}

/**
 * The signed-in organization's own analyses.
 *
 * Unlike `getAnalysis`, this one has no anonymous mode. A run with no
 * organization is a capability URL — hold the id, read the result — and a list
 * has no id to hold, so the only thing an unauthenticated version could mean is
 * "everyone's". The 401 copy says the session expired rather than inventing a
 * permissions story, because that is the case a signed-in user actually hits.
 */
export async function listAnalyses(
  query: AnalysisHistoryQuery = {},
  signal?: AbortSignal,
): Promise<AnalysisList> {
  const params = new URLSearchParams()
  if (query.status) params.set('status', query.status)
  if (query.limit !== undefined) params.set('limit', String(query.limit))
  if (query.offset !== undefined) params.set('offset', String(query.offset))
  const suffix = params.toString() ? `?${params.toString()}` : ''

  let res: Response
  try {
    res = await authorizedFetch(`/api/v1/analyses${suffix}`, {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
      signal,
    })
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw error
    throw new ApiError(
      "We couldn't reach the server. Check your connection and try again.",
      0,
    )
  }

  if (!res.ok) {
    const message =
      res.status === 401
        ? 'Your session has expired. Sign in again to see your analyses.'
        : await readErrorMessage(res)
    throw new ApiError(message, res.status)
  }

  return (await res.json()) as AnalysisList
}

export async function listSeoProjects(signal?: AbortSignal): Promise<SeoProject[]> {
  let res: Response
  try {
    res = await authorizedFetch('/api/v1/seo-projects', {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
      signal,
    })
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw error
    throw new ApiError(
      "We couldn't reach the server. Check your connection and try again.",
      0,
    )
  }

  if (!res.ok) {
    const message =
      res.status === 401
        ? 'Your session has expired. Sign in again to view your Site Audit projects.'
        : await readErrorMessage(res)
    throw new ApiError(message, res.status)
  }

  return (await res.json()) as SeoProject[]
}

export async function createSeoProject(
  input: CreateSeoProjectInput,
): Promise<SeoProject> {
  let res: Response
  try {
    res = await authorizedFetch('/api/v1/seo-projects', {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(input),
    })
  } catch {
    throw new ApiError(
      "We couldn't reach the server. Check your connection and try again.",
      0,
    )
  }

  if (!res.ok) {
    const message =
      res.status === 401
        ? 'Your session has expired. Sign in again to start a Site Audit.'
        : res.status === 409
          ? 'A Site Audit project for this domain already exists.'
          : res.status === 404
            ? // The enqueue routes 404 while the site-audit worker is not
              // deployed (config.site_audit_enabled). Give the caller an honest
              // reason instead of a bare "Not Found".
              'Site Audit is not available in this deployment yet.'
            : await readErrorMessage(res)
    throw new ApiError(message, res.status)
  }

  return (await res.json()) as SeoProject
}

export async function getSeoProject(
  projectId: string,
  signal?: AbortSignal,
): Promise<SeoProjectDetail> {
  let res: Response
  try {
    res = await authorizedFetch(`/api/v1/seo-projects/${encodeURIComponent(projectId)}`, {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
      signal,
    })
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw error
    throw new ApiError(
      "We couldn't reach the server. Check your connection and try again.",
      0,
    )
  }

  if (!res.ok) {
    const message =
      res.status === 401
        ? 'Your session has expired. Sign in again to view this Site Audit.'
        : res.status === 404 || res.status === 422
          ? "We couldn't find that SEO project."
          : await readErrorMessage(res)
    throw new ApiError(message, res.status)
  }

  return (await res.json()) as SeoProjectDetail
}

export async function getSiteAudit(
  projectId: string,
  auditId: string,
  signal?: AbortSignal,
): Promise<SiteAuditDetail> {
  let res: Response
  try {
    res = await authorizedFetch(
      `/api/v1/seo-projects/${encodeURIComponent(projectId)}/audits/${encodeURIComponent(auditId)}`,
      {
        headers: { Accept: 'application/json' },
        cache: 'no-store',
        signal,
      },
    )
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw error
    throw new ApiError(
      "We couldn't reach the server. Check your connection and try again.",
      0,
    )
  }

  if (!res.ok) {
    const message =
      res.status === 401
        ? 'Your session has expired. Sign in again to view this Site Audit.'
        : res.status === 404 || res.status === 422
          ? "We couldn't find that audit run."
          : await readErrorMessage(res)
    throw new ApiError(message, res.status)
  }

  return (await res.json()) as SiteAuditDetail
}

// --- Administration -------------------------------------------------------
//
// Thin clients over `/api/v1/admin/*`. They deliberately carry no permission
// logic: the API decides, and a 403 here is the answer rather than something to
// pre-empt. The UI hides controls the caller cannot use as a courtesy, not as a
// security boundary.

export async function fetchOrganization(): Promise<AdminOrganization> {
  const res = await authorizedFetch('/api/v1/admin/organization')
  if (!res.ok) throw new ApiError(await readErrorMessage(res), res.status)
  return (await res.json()) as AdminOrganization
}

export interface MemberQuery {
  q?: string
  status?: string
  role?: string
  limit?: number
  offset?: number
}

export async function fetchMembers(query: MemberQuery = {}): Promise<AdminMemberList> {
  const params = new URLSearchParams()
  if (query.q) params.set('q', query.q)
  if (query.status) params.set('status', query.status)
  if (query.role) params.set('role', query.role)
  if (query.limit != null) params.set('limit', String(query.limit))
  if (query.offset != null) params.set('offset', String(query.offset))

  const suffix = params.toString() ? `?${params}` : ''
  const res = await authorizedFetch(`/api/v1/admin/members${suffix}`)
  if (!res.ok) throw new ApiError(await readErrorMessage(res), res.status)
  return (await res.json()) as AdminMemberList
}

export async function updateMember(
  userId: string,
  changes: { role?: string; status?: string },
): Promise<AdminMember> {
  const res = await authorizedFetch(`/api/v1/admin/members/${encodeURIComponent(userId)}`, {
    method: 'PATCH',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(changes),
  })
  if (!res.ok) throw new ApiError(await readErrorMessage(res), res.status)
  return (await res.json()) as AdminMember
}

export async function removeMember(userId: string): Promise<void> {
  const res = await authorizedFetch(`/api/v1/admin/members/${encodeURIComponent(userId)}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new ApiError(await readErrorMessage(res), res.status)
}

// --- Invitations ----------------------------------------------------------

export interface InvitationQuery {
  q?: string
  status?: string
  limit?: number
  offset?: number
}

export async function fetchInvitations(
  query: InvitationQuery = {},
): Promise<AdminInvitationList> {
  const params = new URLSearchParams()
  if (query.q) params.set('q', query.q)
  if (query.status) params.set('status', query.status)
  if (query.limit != null) params.set('limit', String(query.limit))
  if (query.offset != null) params.set('offset', String(query.offset))

  const suffix = params.toString() ? `?${params}` : ''
  const res = await authorizedFetch(`/api/v1/admin/invitations${suffix}`)
  if (!res.ok) throw new ApiError(await readErrorMessage(res), res.status)
  return (await res.json()) as AdminInvitationList
}

export async function createInvitation(
  email: string,
  role: string,
): Promise<AdminInvitationCreated> {
  const res = await authorizedFetch('/api/v1/admin/invitations', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ email, role }),
  })
  if (!res.ok) throw new ApiError(await readErrorMessage(res), res.status)
  return (await res.json()) as AdminInvitationCreated
}

export async function resendInvitation(id: string): Promise<AdminInvitationCreated> {
  const res = await authorizedFetch(
    `/api/v1/admin/invitations/${encodeURIComponent(id)}/resend`,
    { method: 'POST' },
  )
  if (!res.ok) throw new ApiError(await readErrorMessage(res), res.status)
  return (await res.json()) as AdminInvitationCreated
}

export async function revokeInvitation(id: string): Promise<AdminInvitation> {
  const res = await authorizedFetch(`/api/v1/admin/invitations/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new ApiError(await readErrorMessage(res), res.status)
  return (await res.json()) as AdminInvitation
}

// The two public halves of the flow. Neither is authorized — the token IS the
// credential — so both use plain `fetch`. A signed-in caller's bearer is passed
// on the accept, because an existing user joining a second organization must be
// recognized rather than told their address is taken.
export async function previewInvitation(token: string): Promise<InvitationPreview> {
  const res = await fetch(`/api/v1/invitations/${encodeURIComponent(token)}`, {
    headers: { Accept: 'application/json' },
    cache: 'no-store',
  })
  if (!res.ok) throw new ApiError(await readErrorMessage(res), res.status)
  return (await res.json()) as InvitationPreview
}

export async function acceptInvitation(
  token: string,
  password: string,
): Promise<LoginResponse> {
  const res = await authorizedFetch(
    `/api/v1/invitations/${encodeURIComponent(token)}/accept`,
    {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ password }),
    },
  )
  if (!res.ok) throw new ApiError(await readErrorMessage(res), res.status)
  return (await res.json()) as LoginResponse
}

// --- Sessions / devices ----------------------------------------------------
//
// Self-service session management. All three are self-scoped server-side: the
// list and the revocations only ever touch the caller's own sessions, and a
// session id that is not theirs answers 404 without confirming it exists.

export async function fetchSessions(): Promise<AuthSessionList> {
  const res = await authorizedFetch('/api/v1/auth/sessions')
  if (!res.ok) throw new ApiError(await readErrorMessage(res), res.status)
  return (await res.json()) as AuthSessionList
}

export async function revokeSession(sessionId: string): Promise<void> {
  const res = await authorizedFetch(
    `/api/v1/auth/sessions/${encodeURIComponent(sessionId)}`,
    { method: 'DELETE' },
  )
  // 404 is the answer for a session that is not the caller's — surface it as a
  // gone-already rather than a raw failure, since the goal (it is not active)
  // is met either way.
  if (!res.ok && res.status !== 404) {
    throw new ApiError(await readErrorMessage(res), res.status)
  }
}

export async function revokeAllSessions(): Promise<SessionRevokeAllResult> {
  const res = await authorizedFetch('/api/v1/auth/sessions/revoke-all', {
    method: 'POST',
  })
  if (!res.ok) throw new ApiError(await readErrorMessage(res), res.status)
  return (await res.json()) as SessionRevokeAllResult
}

// --- Audit log ------------------------------------------------------------

export interface AuditQuery {
  q?: string
  action?: string
  actor_id?: string
  entity_type?: string
  entity_id?: string
  outcome?: string
  occurred_from?: string
  occurred_to?: string
  sort?: string
  order?: 'asc' | 'desc'
  limit?: number
  offset?: number
}

export async function fetchAuditEvents(query: AuditQuery = {}): Promise<AuditEventList> {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== '') {
      params.set(key, String(value))
    }
  }
  const suffix = params.toString() ? `?${params}` : ''
  const res = await authorizedFetch(`/api/v1/admin/audit-events${suffix}`)
  if (!res.ok) throw new ApiError(await readErrorMessage(res), res.status)
  return (await res.json()) as AuditEventList
}

export async function fetchRecordHistory(
  entityType: string,
  entityId: string,
): Promise<AuditEventList> {
  const res = await authorizedFetch(
    `/api/v1/admin/audit-events/history/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}`,
  )
  if (!res.ok) throw new ApiError(await readErrorMessage(res), res.status)
  return (await res.json()) as AuditEventList
}

export async function fetchAuditIntegrity(): Promise<AuditIntegrity> {
  const res = await authorizedFetch('/api/v1/admin/audit-events/integrity')
  if (!res.ok) throw new ApiError(await readErrorMessage(res), res.status)
  return (await res.json()) as AuditIntegrity
}

// --- Backlink Intelligence (P8.3) -----------------------------------------
//
// Every route here lives behind BACKLINKS_ENABLED and answers 404 when it is
// off — deliberately the same 404 an unknown project gets, so the flag does not
// announce the feature. That makes a bare 404 ambiguous to the client, and
// `useBacklinkProfile` resolves it by asking a question these routes cannot
// answer: whether the SEO project itself loads. Project fine + backlinks 404
// means the module is off, not that anything is missing.
//
// So these functions must NOT rewrite a 404 into a friendly sentence the way
// the Site Audit calls do — the caller needs the raw status to make that
// distinction. They pass the status through on ApiError and let the hook decide.

async function backlinkFetch(path: string, signal?: AbortSignal): Promise<Response> {
  try {
    return await authorizedFetch(path, {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
      signal,
    })
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw error
    throw new ApiError(
      "We couldn't reach the server. Check your connection and try again.",
      0,
    )
  }
}

async function backlinkJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await backlinkFetch(path, signal)
  if (!res.ok) {
    const message =
      res.status === 401
        ? 'Your session has expired. Sign in again to view backlinks.'
        : await readErrorMessage(res)
    throw new ApiError(message, res.status)
  }
  return (await res.json()) as T
}

function backlinksBase(projectId: string): string {
  return `/api/v1/seo-projects/${encodeURIComponent(projectId)}/backlinks`
}

export async function getBacklinkSummary(
  projectId: string,
  signal?: AbortSignal,
): Promise<BacklinkSummary> {
  return backlinkJson<BacklinkSummary>(`${backlinksBase(projectId)}/summary`, signal)
}

export interface BacklinkInventoryQuery {
  status?: string
  anchor_class?: string
  follow?: boolean
  source_domain?: string
  min_authority?: number
  sort?: string
  limit?: number
  offset?: number
}

export async function listBacklinks(
  projectId: string,
  query: BacklinkInventoryQuery = {},
  signal?: AbortSignal,
): Promise<BacklinkPage> {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== '') {
      params.set(key, String(value))
    }
  }
  const suffix = params.toString() ? `?${params.toString()}` : ''
  return backlinkJson<BacklinkPage>(`${backlinksBase(projectId)}${suffix}`, signal)
}

export async function listReferringDomains(
  projectId: string,
  query: { band?: string; sort?: string; limit?: number; offset?: number } = {},
  signal?: AbortSignal,
): Promise<ReferringDomainPage> {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== '') {
      params.set(key, String(value))
    }
  }
  const suffix = params.toString() ? `?${params.toString()}` : ''
  return backlinkJson<ReferringDomainPage>(
    `${backlinksBase(projectId)}/referring-domains${suffix}`,
    signal,
  )
}

export async function listLinkEvents(
  projectId: string,
  query: { kind?: string; limit?: number; offset?: number } = {},
  signal?: AbortSignal,
): Promise<LinkEventPage> {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== '') {
      params.set(key, String(value))
    }
  }
  const suffix = params.toString() ? `?${params.toString()}` : ''
  return backlinkJson<LinkEventPage>(
    `${backlinksBase(projectId)}/events${suffix}`,
    signal,
  )
}

export async function getBacklinkOpportunities(
  projectId: string,
  signal?: AbortSignal,
): Promise<BacklinkOpportunities> {
  return backlinkJson<BacklinkOpportunities>(
    `${backlinksBase(projectId)}/opportunities`,
    signal,
  )
}

export async function refreshBacklinks(
  projectId: string,
): Promise<BacklinkRefreshResult> {
  let res: Response
  try {
    res = await authorizedFetch(`${backlinksBase(projectId)}/refresh`, {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify({ trigger: 'manual' }),
    })
  } catch {
    throw new ApiError(
      "We couldn't reach the server. Check your connection and try again.",
      0,
    )
  }

  if (!res.ok) {
    // These four are the ones a customer can act on, so each says what happened
    // rather than "request failed". 402 and 429 are separate on purpose: one is
    // "top up", the other is "wait for next month" — the backend keeps them
    // distinct and collapsing them here would throw that away.
    const message =
      res.status === 403
        ? 'Your role cannot start a backlink refresh. Ask an Analyst or above.'
        : res.status === 409
          ? 'A refresh is already running for this project.'
          : res.status === 429
            ? "This organization has used its backlink refreshes for the month."
            : res.status === 402
              ? 'Not enough credit to run a backlink refresh.'
              : res.status === 503
                ? 'No backlink index is configured yet, so there is nothing to refresh.'
                : await readErrorMessage(res)
    throw new ApiError(message, res.status)
  }

  return (await res.json()) as BacklinkRefreshResult
}

// Exports must be FETCHED, not linked.
//
// The obvious implementation — an <a href> straight at the route — silently
// fails here: the access token is a bearer token held in memory on purpose
// (never a cookie, never localStorage — see lib/session.ts), and a plain link
// navigation carries no Authorization header. The download would 401, and it
// would do so as a page navigation, so the customer would see a raw error body
// rather than anything this app controls.
//
// So the file comes back through the same authorized fetch as everything else
// and is handed to the browser as a blob.
export interface DownloadedFile {
  blob: Blob
  filename: string
}

function filenameFrom(res: Response, fallback: string): string {
  const disposition = res.headers.get('Content-Disposition') ?? ''
  const match = /filename="?([^"]+)"?/.exec(disposition)
  return match?.[1] ?? fallback
}

async function downloadExport(
  path: string,
  fallbackName: string,
  subject: string,
): Promise<DownloadedFile> {
  let res: Response
  try {
    res = await authorizedFetch(path, { cache: 'no-store' })
  } catch {
    throw new ApiError(
      "We couldn't reach the server. Check your connection and try again.",
      0,
    )
  }

  if (!res.ok) {
    const message =
      res.status === 403
        ? `Your role cannot export ${subject}. Exporting is a separate permission from viewing.`
        : res.status === 401
          ? 'Your session has expired. Sign in again to export.'
          : await readErrorMessage(res)
    throw new ApiError(message, res.status)
  }

  return { blob: await res.blob(), filename: filenameFrom(res, fallbackName) }
}

export async function downloadBacklinkCsv(projectId: string): Promise<DownloadedFile> {
  return downloadExport(
    `${backlinksBase(projectId)}/export.csv`,
    'backlinks.csv',
    'backlinks',
  )
}

export async function downloadDisavowFile(projectId: string): Promise<DownloadedFile> {
  return downloadExport(
    `${backlinksBase(projectId)}/disavow.txt`,
    'disavow.txt',
    'the disavow file',
  )
}
