import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import SerpVisibility from '@/components/SerpVisibility'
import type { SerpCheck, SerpVisibility as SerpData } from '@/lib/contracts'

function check(overrides: Partial<SerpCheck> = {}): SerpCheck {
  return {
    id: 'c1',
    query: 'best warehouse robots',
    source: 'searxng',
    hit: false,
    rank: null,
    matched_url: null,
    matched_snippet: null,
    matched_via: null,
    result_count: 10,
    unresponsive_engines: null,
    ...overrides,
  }
}

function serp(overrides: Partial<SerpData> = {}): SerpData {
  return {
    status: 'ok',
    source: 'searxng',
    score: 0.5,
    hits: 1,
    queries: 2,
    checks: [],
    ...overrides,
  }
}

describe('SerpVisibility', () => {
  it('reports the hit rate as a count, not only a bar', () => {
    render(<SerpVisibility serp={serp()} />)

    expect(screen.getByText('Appeared in 1 of 2 searches')).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toHaveAttribute(
      'aria-valuenow',
      '50',
    )
  })

  it('lists each search with its rank when the brand appeared', () => {
    render(
      <SerpVisibility
        serp={serp({
          checks: [
            check({
              id: 'c1',
              hit: true,
              rank: 3,
              matched_url: 'https://acme.example/',
              matched_via: 'domain',
            }),
            check({ id: 'c2', query: 'warehouse robots reviews' }),
          ],
        })}
      />,
    )

    expect(screen.getByText('best warehouse robots')).toBeInTheDocument()
    expect(screen.getByText(/Yes, position 3/)).toBeInTheDocument()
    expect(screen.getByText('https://acme.example/')).toBeInTheDocument()
    expect(screen.getByText('No')).toBeInTheDocument()
    expect(
      screen.getByText('Not found in the first 10 results.'),
    ).toBeInTheDocument()
  })

  it('explains an unmeasured run instead of drawing a zero', () => {
    render(
      <SerpVisibility
        serp={serp({ status: 'unavailable', score: null, hits: 0, queries: 0 })}
      />,
    )

    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
    expect(screen.queryByText(/0%/)).not.toBeInTheDocument()
    expect(screen.getByText(/could not read search results/i)).toBeInTheDocument()
  })

  it('explains a profile with nothing worth searching for', () => {
    render(
      <SerpVisibility
        serp={serp({ status: 'no_topics', score: null, hits: 0, queries: 0 })}
      />,
    )

    expect(
      screen.getByText(/did not give us a product category/i),
    ).toBeInTheDocument()
  })

  it('keeps unreadable searches out of the table and says how many there were', () => {
    render(
      <SerpVisibility
        serp={serp({
          score: 1,
          hits: 1,
          queries: 1,
          checks: [
            check({ id: 'c1', hit: true, rank: 1, matched_url: 'https://acme.example/' }),
            check({
              id: 'c2',
              query: 'warehouse robots comparison',
              hit: null,
              result_count: 0,
              unresponsive_engines: 'brave, duckduckgo',
            }),
          ],
        })}
      />,
    )

    // The unreadable query is not presented as a miss...
    expect(
      screen.queryByText('warehouse robots comparison'),
    ).not.toBeInTheDocument()
    // ...but its absence is accounted for.
    expect(
      screen.getByText(/1 search could not be read/i),
    ).toBeInTheDocument()
  })

  it('renders a measured run that found nothing without a table row claiming otherwise', () => {
    render(
      <SerpVisibility
        serp={serp({ score: 0, hits: 0, queries: 1, checks: [check()] })}
      />,
    )

    expect(screen.getByText('Appeared in 0 of 1 searches')).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toHaveAttribute(
      'aria-valuenow',
      '0',
    )
  })

  it('survives a hit with no rank', () => {
    render(
      <SerpVisibility
        serp={serp({
          checks: [check({ hit: true, rank: null, matched_url: 'https://acme.example/' })],
        })}
      />,
    )

    expect(screen.getByText(/position unknown/i)).toBeInTheDocument()
  })
})
