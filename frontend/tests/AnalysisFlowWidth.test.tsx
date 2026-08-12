import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'

const RUNNING = {
  id: 'a1',
  status: 'running',
  progress: 40,
  current_step: 'prompting',
  created_at: '2026-08-12T09:00:00Z',
  error: null,
  result: {},
  input: { domain: 'acme.test' },
}

vi.mock('next/navigation', () => ({
  usePathname: () => '/ai-visibility',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}))

// The shell is the other half of the page and has its own tests; here it would
// only drag in providers that say nothing about content width.
vi.mock('@/components/shell/AppShell', () => ({
  default: ({ children }: { children: ReactNode }) => <>{children}</>,
}))

vi.mock('@/components/AnalysisSessionProvider', () => ({
  useAnalysisSession: () => ({ analysisId: 'a1', setAnalysisId: vi.fn() }),
}))

vi.mock('@/lib/api', () => ({
  getAnalysis: vi.fn(async () => RUNNING),
  listAnalyses: vi.fn(async () => ({
    items: [],
    total: 0,
    limit: 20,
    offset: 0,
  })),
  ApiError: class ApiError extends Error {
    status = 500
  },
}))

vi.mock('@/components/ai-visibility/useAnalysisQuery', () => ({
  useAnalysisQuery: () => ({
    analysisId: 'a1',
    status: 'running',
    analysis: RUNNING,
    error: null,
  }),
}))

import AiOverviewClient from '@/app/ai-visibility/OverviewClient'
import SearchOverviewClient from '@/app/search-visibility/OverviewClient'
import AnalysisBoundSubpage from '@/components/ai-visibility/AnalysisBoundSubpage'
import AnalysisHistoryClient from '@/app/analyses/AnalysisHistoryClient'

/** The width class on the box that actually holds the page's content. */
function contentWidth(container: HTMLElement): string {
  const box = container.querySelector('.mx-auto')
  expect(box, 'the screen renders a centred content container').not.toBeNull()
  const width = [...box!.classList].find((name) => name.startsWith('max-w-'))
  expect(width, 'the content container declares a width').toBeDefined()
  return width!
}

/**
 * A reader watching an analysis run switches tabs while they wait. Every tab
 * showed the same StepProgress in a differently sized box — 768px on Overview,
 * 1024px on Prompts — so the content jumped sideways on each switch, and again
 * on Overview when the run finished into a 1152px dashboard.
 */
describe('analysis flow content width', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockReturnValue({
        matches: true,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    )
  })

  it('holds a running analysis at the same width on every tab', async () => {
    const overview = render(<AiOverviewClient />)
    await waitFor(() =>
      expect(screen.getByText('Running analysis…')).toBeInTheDocument(),
    )
    const overviewWidth = contentWidth(overview.container)
    overview.unmount()

    const subpage = render(
      <AnalysisBoundSubpage title="Prompts">{() => null}</AnalysisBoundSubpage>,
    )
    const subpageWidth = contentWidth(subpage.container)
    subpage.unmount()

    const search = render(<SearchOverviewClient />)
    const searchWidth = contentWidth(search.container)

    expect(subpageWidth).toBe(overviewWidth)
    expect(searchWidth).toBe(overviewWidth)
  })

  it('does not move the box when the run finishes', async () => {
    // The finished dashboard is where the reader ends up; a running screen at a
    // different width means the page reflows the moment results arrive.
    const { default: OverviewDashboard } = await import(
      '@/components/ai-visibility/OverviewDashboard'
    )
    const running = render(<AiOverviewClient />)
    await waitFor(() =>
      expect(screen.getByText('Running analysis…')).toBeInTheDocument(),
    )
    const runningWidth = contentWidth(running.container)
    running.unmount()

    const ready = render(
      <OverviewDashboard
        model={{
          domain: 'acme.test',
          geoScore: 42,
          citeRate: 0.18,
          reliability: 0.77,
          citations: [],
          interventions: [],
          isSample: false,
          analysisId: 'a1',
        }}
      />,
    )

    expect(contentWidth(ready.container)).toBe(runningWidth)
  })

  /**
   * Home is where a signed-in reader starts, and Analyses is the one link off
   * it that leads anywhere. The history sat at 1024px and a single result at
   * 896px, so the same journey shifted twice more after the tabs were settled.
   */
  it('holds the history and a single result at that same width', async () => {
    const history = render(<AnalysisHistoryClient />)
    await waitFor(() =>
      expect(screen.getByText('Your analyses')).toBeInTheDocument(),
    )
    const historyWidth = contentWidth(history.container)
    history.unmount()

    const running = render(<AiOverviewClient />)
    await waitFor(() =>
      expect(screen.getByText('Running analysis…')).toBeInTheDocument(),
    )

    expect(historyWidth).toBe(contentWidth(running.container))
  })
})
