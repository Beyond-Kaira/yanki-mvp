import { describe, expect, it } from 'vitest'
import {
  attributePromptApiError,
  commaToList,
  draftToKycPatch,
  draftsToPatchItems,
  kycToDraft,
  promptLeaksBrand,
  validatePromptDrafts,
} from '@/lib/guided-analysis'
import type { KYC } from '@/lib/contracts'

const sampleKyc: KYC = {
  company: 'Acme Robotics',
  description: 'Warehouse automation',
  industry: 'Robotics',
  category: 'warehouse robots',
  aliases: [],
  products: [],
  services: [],
  keywords: ['automation'],
  locations: ['Türkiye'],
  competitors: ['Globex'],
}

describe('guided-analysis helpers', () => {
  it('converts comma lists and builds a partial KYC patch', () => {
    const original = kycToDraft({
      company: 'Acme',
      description: 'Robots',
      industry: 'Tech',
      category: 'warehouse robots',
      aliases: [],
      products: [],
      services: [],
      keywords: ['automation'],
      locations: [],
      competitors: [],
    })
    const edited = {
      ...original,
      company: 'Acme Robotics',
      keywords: 'automation, logistics',
    }

    expect(commaToList('a, b ,c')).toEqual(['a', 'b', 'c'])
    expect(draftToKycPatch(edited, original)).toEqual({
      company: 'Acme Robotics',
      keywords: ['automation', 'logistics'],
    })
  })

  it('maps prompt drafts to patch items', () => {
    expect(
      draftsToPatchItems([
        { id: '11111111-1111-1111-1111-111111111111', text: 'Best tools?', category: 'recommendation' },
        { text: 'Who leads the market?', category: 'custom' },
      ]),
    ).toEqual([
      {
        id: '11111111-1111-1111-1111-111111111111',
        text: 'Best tools?',
        category: 'recommendation',
      },
      { id: null, text: 'Who leads the market?', category: 'custom' },
    ])
  })

  it('flags brand leaks on category prompts but not custom prompts', () => {
    expect(
      promptLeaksBrand('What are the best Acme Robotics options?', [
        'acme robotics',
      ]),
    ).toBe(true)

    const errors = validatePromptDrafts(
      [
        {
          text: 'What are the best Acme Robotics warehouse options?',
          category: 'recommendation',
        },
        {
          text: 'Which one is better, acme or globex?',
          category: 'custom',
        },
      ],
      sampleKyc,
    )

    expect(errors[0]).toMatch(/brand/i)
    expect(errors[1]).toBeUndefined()
  })

  it('attributes API brand errors to matching prompt rows', () => {
    const message = 'category prompts must not name the brand being measured'
    const attributed = attributePromptApiError(
      message,
      [
        {
          text: 'What are the best Acme Robotics warehouse options?',
          category: 'recommendation',
        },
      ],
      sampleKyc,
    )
    expect(attributed[0]).toBe(message)
  })
})
