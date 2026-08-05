import type {
  Analysis,
  CheckerSubmitResponse,
  CreateAnalysisResponse,
    CreateSeoProjectInput,
    SeoProject,
    SeoProjectDetail,
    SiteAuditDetail,
  WaitlistSignupResponse,
} from './contracts'
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
  const token = getAccessToken()
  const res = token
    ? await fetch(path, withBearer(init, token))
    : await fetch(path, { ...init, credentials: 'same-origin' })

  if (res.status !== 401) return res

  const refreshed = await refreshAccessToken()
  if (!refreshed) return res

  return fetch(path, withBearer(init, refreshed))
}

export async function createAnalysis(url: string): Promise<CreateAnalysisResponse> {
  const res = await fetch('/api/v1/analyses', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  })
  if (!res.ok) {
    const message =
      res.status === 422
        ? "That doesn't look like a valid URL. Use http:// or https://."
        : await readErrorMessage(res)
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

export async function getAnalysis(id: string): Promise<Analysis> {
  const res = await fetch(`/api/v1/analyses/${encodeURIComponent(id)}`, {
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
