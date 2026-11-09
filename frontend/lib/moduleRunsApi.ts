import { authorizedFetch } from '@/lib/api'

export type BrandContextOut = {
  id: string
  brand: string
  source_url: string | null
}

export type ModuleRunOut = {
  id: string
  status: string
  job_kind: string
  linked_analysis_id: string | null
  error: string | null
}

export async function createKycProfile(body: {
  source_url: string
  locale?: string
}): Promise<BrandContextOut> {
  const res = await authorizedFetch('/api/v1/kyc/profiles', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json() as Promise<BrandContextOut>
}

export async function createAiVisibilityRun(body: {
  brand_context_id: string
  mode: 'simulated' | 'measured'
  prompts: { text: string; category: string }[]
}): Promise<ModuleRunOut> {
  const res = await authorizedFetch('/api/v1/ai-visibility/runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json() as Promise<ModuleRunOut>
}

export async function getBackgroundJob(jobId: string): Promise<ModuleRunOut> {
  const res = await authorizedFetch(
    `/api/v1/background-jobs/${encodeURIComponent(jobId)}`,
    { headers: { Accept: 'application/json' }, cache: 'no-store' },
  )
  if (!res.ok) throw new Error(await res.text())
  return res.json() as Promise<ModuleRunOut>
}
