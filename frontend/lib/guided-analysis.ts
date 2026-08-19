import type { KYC, PatchAnalysisKycRequest, Prompt, PromptPatchItem } from '@/lib/contracts'

/** Matches backend ``ALLOWED_PROMPT_CATEGORIES`` (guided PATCH). */
export const PROMPT_CATEGORIES = [
  'recommendation',
  'makers',
  'comparison',
  'alternatives',
  'best-of',
  'use-case',
  'brand-probe',
  'custom',
] as const

export const MAX_USER_PROMPTS = 3

export type KycDraft = {
  company: string
  description: string
  industry: string
  category: string
  aliases: string
  products: string
  services: string
  keywords: string
  use_cases: string
  locations: string
  competitors: string
}

export type PromptDraft = {
  id?: string
  text: string
  category: string
  source?: string
  locked?: boolean
  editable?: boolean
}

export function listToComma(items: string[] | undefined): string {
  return (items ?? []).filter(Boolean).join(', ')
}

export function commaToList(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

export function kycToDraft(kyc: KYC): KycDraft {
  return {
    company: kyc.company ?? '',
    description: kyc.description ?? '',
    industry: kyc.industry ?? '',
    category: kyc.category ?? '',
    aliases: listToComma(kyc.aliases),
    products: listToComma(kyc.products),
    services: listToComma(kyc.services),
    keywords: listToComma(kyc.keywords),
    use_cases: listToComma(kyc.use_cases),
    locations: listToComma(kyc.locations),
    competitors: listToComma(kyc.competitors),
  }
}

export function draftToKycPatch(
  draft: KycDraft,
  original: KycDraft,
): PatchAnalysisKycRequest {
  const patch: PatchAnalysisKycRequest = {}
  const scalarKeys = [
    'company',
    'description',
    'industry',
    'category',
  ] as const
  for (const key of scalarKeys) {
    if (draft[key] !== original[key]) {
      patch[key] = draft[key]
    }
  }
  const listKeys = [
    'aliases',
    'products',
    'services',
    'keywords',
    'use_cases',
    'locations',
    'competitors',
  ] as const
  for (const key of listKeys) {
    if (draft[key] !== original[key]) {
      patch[key] = commaToList(draft[key])
    }
  }
  return patch
}

export function promptsToDrafts(prompts: Prompt[]): PromptDraft[] {
  return prompts.map((prompt) => ({
    id: prompt.id,
    text: prompt.text,
    category: prompt.category,
    source: prompt.source,
    locked: prompt.locked,
    editable: prompt.editable,
  }))
}

export function draftsToPatchItems(drafts: PromptDraft[]): PromptPatchItem[] {
  return drafts.map((draft) => ({
    id: draft.id ?? null,
    text: draft.text.trim(),
    category: draft.category,
  }))
}

export function countNewUserPrompts(drafts: PromptDraft[]): number {
  return drafts.filter((draft) => !draft.id).length
}

const MIN_BRAND_KEY_LEN = 2
const BRAND_PROBE_CATEGORY = 'brand-probe'

/** Normalized comparison form — mirrors backend ``normalize_key`` closely enough for UI hints. */
export function normalizePromptKey(value: string): string {
  return value
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[\W_]+/g, ' ')
    .trim()
}

function containsPromptKey(haystackKey: string, needle: string): boolean {
  const normalized = normalizePromptKey(needle)
  if (!normalized) return false
  return ` ${haystackKey} `.includes(` ${normalized} `)
}

export function brandKeysFromKyc(kyc: KYC | null): string[] {
  if (!kyc) return []
  const keys = new Set<string>()
  for (const name of [kyc.company, ...(kyc.aliases ?? [])]) {
    const cleaned = (name ?? '').trim()
    if (cleaned.length < MIN_BRAND_KEY_LEN) continue
    const key = normalizePromptKey(cleaned)
    if (key) keys.add(key)
  }
  return [...keys].sort()
}

export function promptLeaksBrand(text: string, brandKeys: string[]): boolean {
  const haystack = normalizePromptKey(text)
  return brandKeys.some((key) => containsPromptKey(haystack, key))
}

export function firstPromptErrorIndex(errors: Record<number, string>): number | null {
  const indices = Object.keys(errors)
    .map((key) => Number(key))
    .filter((index) => Number.isFinite(index))
    .sort((left, right) => left - right)
  return indices.length > 0 ? indices[0]! : null
}

/** Client-side checks aligned with guided PATCH validation (per-row errors). */
export function validatePromptDrafts(
  drafts: PromptDraft[],
  kyc: KYC | null,
): Record<number, string> {
  const errors: Record<number, string> = {}
  if (drafts.length === 0) {
    return { 0: 'Keep at least one prompt.' }
  }

  const brandKeys = brandKeysFromKyc(kyc)
  const seenText = new Map<string, number>()

  drafts.forEach((draft, index) => {
    const text = draft.text.trim()

    if (text.length < 3) {
      errors[index] = 'Question needs at least three characters.'
      return
    }

    if (
      !PROMPT_CATEGORIES.includes(
        draft.category as (typeof PROMPT_CATEGORIES)[number],
      )
    ) {
      errors[index] = 'Choose a valid category.'
      return
    }

    if (
      draft.category !== BRAND_PROBE_CATEGORY &&
      draft.category !== 'custom' &&
      promptLeaksBrand(text, brandKeys)
    ) {
      errors[index] = 'Category prompts must not name the brand being measured.'
      return
    }

    const folded = text.toLowerCase()
    const duplicateOf = seenText.get(folded)
    if (duplicateOf !== undefined) {
      errors[index] = 'This question is duplicated.'
      if (errors[duplicateOf] === undefined) {
        errors[duplicateOf] = 'This question is duplicated.'
      }
      return
    }
    seenText.set(folded, index)
  })

  return errors
}

/** Map a PATCH 422 message onto prompt rows when the backend gives no index. */
export function attributePromptApiError(
  message: string,
  drafts: PromptDraft[],
  kyc: KYC | null,
): Record<number, string> {
  const lower = message.toLowerCase()
  const brandKeys = brandKeysFromKyc(kyc)
  const errors: Record<number, string> = {}

  if (lower.includes('brand')) {
    drafts.forEach((draft, index) => {
      if (
        draft.category !== BRAND_PROBE_CATEGORY &&
        promptLeaksBrand(draft.text, brandKeys)
      ) {
        errors[index] = message
      }
    })
    if (Object.keys(errors).length > 0) return errors
  }

  if (lower.includes('too short')) {
    drafts.forEach((draft, index) => {
      if (draft.text.trim().length < 3) {
        errors[index] = message
      }
    })
    if (Object.keys(errors).length > 0) return errors
  }

  if (lower.includes('duplicate')) {
    const seen = new Map<string, number>()
    drafts.forEach((draft, index) => {
      const folded = draft.text.trim().toLowerCase()
      const prior = seen.get(folded)
      if (prior !== undefined) {
        errors[index] = message
        errors[prior] = message
      } else {
        seen.set(folded, index)
      }
    })
    if (Object.keys(errors).length > 0) return errors
  }

  if (lower.includes('category')) {
    drafts.forEach((draft, index) => {
      if (
        !PROMPT_CATEGORIES.includes(
          draft.category as (typeof PROMPT_CATEGORIES)[number],
        )
      ) {
        errors[index] = message
      }
    })
    if (Object.keys(errors).length > 0) return errors
  }

  return errors
}

export function analysisStatusLabel(status: string): string {
  if (status === 'awaiting_review') return 'Awaiting review'
  return status
}
