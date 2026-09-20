import { authorizedFetch, readErrorMessage } from './api'
import type { components } from './types'

// FastAPI serializes defaults on this response; OpenAPI marks those fields optional.
export type IndustryRanking = Required<components['schemas']['IndustryRankingPage']>
export type IndustrySector = components['schemas']['IndustrySector']

export async function fetchIndustrySectors(
  signal?: AbortSignal,
): Promise<IndustrySector[]> {
  const response = await authorizedFetch('/api/v1/industry-citations/sectors', {
    signal,
  })
  if (!response.ok) throw new Error(await readErrorMessage(response))
  return response.json()
}

export async function fetchIndustryRanking(
  sector: string,
  offset = 0,
  signal?: AbortSignal,
): Promise<IndustryRanking> {
  const query = new URLSearchParams({
    sector,
    offset: String(offset),
    limit: '25',
  })
  const response = await authorizedFetch(
    `/api/v1/industry-citations/ranking?${query}`,
    { signal },
  )
  if (!response.ok) throw new Error(await readErrorMessage(response))
  return response.json()
}

export type IndustryQuestionRequest =
  components['schemas']['IndustryQuestionRequest']
export type IndustryQuestionResponse =
  components['schemas']['IndustryQuestionResponse']

export async function generateIndustryQuestions(
  input: IndustryQuestionRequest,
  signal?: AbortSignal,
): Promise<IndustryQuestionResponse> {
  const response = await authorizedFetch(
    '/api/v1/industry-citations/questions',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
      signal,
    },
  )
  if (!response.ok) throw new Error(await readErrorMessage(response))
  return response.json()
}
