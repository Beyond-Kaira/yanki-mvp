import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const push = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  usePathname: () => '/ai-visibility',
}))

vi.mock('@/lib/api', () => ({
  createAnalysis: vi.fn(),
  patchAnalysisKyc: vi.fn(),
  patchAnalysisPrompts: vi.fn(),
  executePromptsAndScore: vi.fn(),
}))

import CustomGeoGuidedWizard from '@/components/guided/CustomGeoGuidedWizard'
import { patchAnalysisPrompts } from '@/lib/api'
import type { Analysis } from '@/lib/contracts'

const mockedPatchPrompts = vi.mocked(patchAnalysisPrompts)

const analysis: Analysis = {
  id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  url: 'https://acme.test',
  status: 'awaiting_review',
  run_mode: 'guided',
  progress: 45,
  current_step: null,
  error: null,
  created_at: '2026-01-01T00:00:00Z',
  geo_score: null,
  footprint_count: null,
  total_responses: null,
  reliability_score: null,
  serp_score: null,
  serp_hit_count: null,
  serp_query_count: null,
  serp_status: null,
  serp_source: null,
  seo_score: null,
  seo_grade: null,
  seo_status: null,
  result: {
    kyc: {
      company: 'Acme',
      description: 'Warehouse automation',
      industry: 'Robotics',
      category: 'warehouse robots',
      aliases: [],
      products: [],
      services: [],
      keywords: ['automation'],
      locations: ['Türkiye'],
      competitors: ['Globex'],
    },
    prompts: [
      {
        id: 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
        text: 'What are the best warehouse robots?',
        category: 'recommendation',
        source: 'generated',
        locked: false,
        editable: true,
      },
    ],
    responses: [],
    geo_score: null,
    footprint_count: null,
    total_responses: null,
    geo_records: [],
    engine_presence: null,
    competitors_appeared: null,
    serp: null,
    seo: null,
  },
}

describe('CustomGeoGuidedWizard', () => {
  beforeEach(() => {
    push.mockReset()
    mockedPatchPrompts.mockReset()
    Element.prototype.scrollIntoView = vi.fn()
  })

  it('shows the profile step first', () => {
    render(
      <CustomGeoGuidedWizard
        analysis={analysis}
        onAnalysisUpdated={vi.fn()}
        onMeasureStarted={vi.fn()}
      />,
    )

    expect(screen.getByRole('heading', { name: /review before measuring/i })).toBeInTheDocument()
    expect(screen.getByLabelText(/company/i)).toHaveValue('Acme')
  })

  it('advances to prompts without saving when unchanged', async () => {
    const user = userEvent.setup()
    render(
      <CustomGeoGuidedWizard
        analysis={analysis}
        onAnalysisUpdated={vi.fn()}
        onMeasureStarted={vi.fn()}
      />,
    )

    await user.click(screen.getByRole('button', { name: /continue without saving/i }))

    expect(await screen.findByRole('heading', { name: /^prompts$/i })).toBeInTheDocument()
    expect(screen.getByDisplayValue('What are the best warehouse robots?')).toBeInTheDocument()
  })

  it('shows a prompt-level error and scrolls to the offending row', async () => {
    const user = userEvent.setup()
    render(
      <CustomGeoGuidedWizard
        analysis={analysis}
        onAnalysisUpdated={vi.fn()}
        onMeasureStarted={vi.fn()}
      />,
    )

    await user.click(screen.getByRole('button', { name: /continue without saving/i }))
    const textarea = screen.getByDisplayValue('What are the best warehouse robots?')
    await user.clear(textarea)
    await user.type(
      textarea,
      'What are the best Acme Robotics warehouse options?',
    )
    await user.click(screen.getByRole('button', { name: /save and continue/i }))

    expect(
      await screen.findByText(/must not name the brand/i),
    ).toBeInTheDocument()
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled()
    expect(mockedPatchPrompts).not.toHaveBeenCalled()
  })
})
