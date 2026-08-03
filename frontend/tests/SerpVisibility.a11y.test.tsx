import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import SerpVisibility from '@/components/SerpVisibility'
import type { SerpCheck, SerpVisibility as SerpData } from '@/lib/contracts'
import { axeCheck } from './a11y'

const checks: SerpCheck[] = [
  {
    id: 'c1',
    query: 'best warehouse robots',
    source: 'searxng',
    hit: true,
    rank: 3,
    matched_url: 'https://acme.example/',
    matched_snippet: 'Acme Robotics — warehouse automation',
    matched_via: 'domain',
    result_count: 10,
    unresponsive_engines: null,
  },
  {
    id: 'c2',
    query: 'warehouse robots comparison',
    source: 'searxng',
    hit: false,
    rank: null,
    matched_url: null,
    matched_snippet: null,
    matched_via: null,
    result_count: 10,
    unresponsive_engines: null,
  },
  {
    id: 'c3',
    query: 'warehouse robots reviews',
    source: 'searxng',
    hit: null,
    rank: null,
    matched_url: null,
    matched_snippet: null,
    matched_via: null,
    result_count: 0,
    unresponsive_engines: 'brave, duckduckgo',
  },
]

const measured: SerpData = {
  status: 'ok',
  source: 'searxng',
  score: 0.5,
  hits: 1,
  queries: 2,
  checks,
}

const unmeasured: SerpData = {
  status: 'unavailable',
  source: 'searxng',
  score: null,
  hits: 0,
  queries: 0,
  checks: [],
}

describe('SerpVisibility accessibility', () => {
  it('has no axe violations across hit, miss and unreadable rows', async () => {
    const { container } = render(
      <main>
        <SerpVisibility serp={measured} />
      </main>,
    )
    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('has no axe violations in the not-measured state', async () => {
    const { container } = render(
      <main>
        <SerpVisibility serp={unmeasured} />
      </main>,
    )
    expect(await axeCheck(container)).toHaveNoViolations()
  })
})
