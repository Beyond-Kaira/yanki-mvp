import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Backlink } from '@/lib/contracts'

/**
 * The inventory table.
 *
 * Its one job that is easy to get subtly wrong: the filter and page state live
 * on the SERVER, because the profile can be six figures of rows. So every
 * control has to actually reach the API, and the reported total has to describe
 * the filter rather than the page — a table that says "25" when the answer is
 * 4,000 has quietly told a customer they have almost no backlinks.
 */

const mockedListBacklinks = vi.hoisted(() => vi.fn())

vi.mock('@/lib/api', () => ({
  listBacklinks: mockedListBacklinks,
}))

import BacklinkInventoryPanel from '@/components/backlinks/inventory/BacklinkInventoryPanel'

function link(overrides: Partial<Backlink> = {}): Backlink {
  return {
    id: overrides.id ?? 'b-1',
    source_url: 'https://news.example/story',
    source_domain: 'news.example',
    target_url: 'https://acme.test/',
    anchor: 'Acme',
    anchor_class: 'brand',
    is_follow: true,
    is_image_link: false,
    tld: 'example',
    status: 'active',
    first_seen_at: '2026-06-01T00:00:00Z',
    last_seen_at: '2026-08-01T00:00:00Z',
    lost_at: null,
    lost_reason: null,
    verified_at: null,
    verify_verdict: null,
    source_domain_authority: 78,
    source_page_authority: 60,
    toxicity_score: null,
    toxicity_band: null,
    vendor: 'mock',
    ...overrides,
  }
}

describe('BacklinkInventoryPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedListBacklinks.mockResolvedValue({
      total: 4000,
      limit: 25,
      offset: 0,
      items: [link()],
    })
  })

  it('reports the filter total, not the page size', async () => {
    render(<BacklinkInventoryPanel projectId="p-1" />)

    expect(await screen.findByText(/4,000 matching links/i)).toBeInTheDocument()
  })

  it('sends the anchor-class filter to the server rather than filtering in place', async () => {
    const user = userEvent.setup()
    render(<BacklinkInventoryPanel projectId="p-1" />)
    await screen.findByText(/4,000 matching links/i)

    await user.selectOptions(
      screen.getByRole('combobox', { name: /filter by anchor class/i }),
      'exact',
    )

    await waitFor(() => {
      expect(mockedListBacklinks).toHaveBeenLastCalledWith(
        'p-1',
        expect.objectContaining({ anchor_class: 'exact' }),
        expect.anything(),
      )
    })
  })

  it('translates the nofollow filter into the boolean the API expects', async () => {
    const user = userEvent.setup()
    render(<BacklinkInventoryPanel projectId="p-1" />)
    await screen.findByText(/4,000 matching links/i)

    await user.selectOptions(
      screen.getByRole('combobox', { name: /filter by link attribute/i }),
      'nofollow',
    )

    await waitFor(() => {
      expect(mockedListBacklinks).toHaveBeenLastCalledWith(
        'p-1',
        expect.objectContaining({ follow: false }),
        expect.anything(),
      )
    })
  })

  it('returns to the first page when a filter changes', async () => {
    const user = userEvent.setup()
    render(<BacklinkInventoryPanel projectId="p-1" />)
    await screen.findByText(/4,000 matching links/i)

    await user.click(screen.getByRole('button', { name: /next/i }))
    await waitFor(() => {
      expect(mockedListBacklinks).toHaveBeenLastCalledWith(
        'p-1',
        expect.objectContaining({ offset: 25 }),
        expect.anything(),
      )
    })

    await user.selectOptions(
      screen.getByRole('combobox', { name: /sort backlinks/i }),
      'toxicity',
    )

    // Staying on page 2 of a filter that now matches four rows renders an empty
    // table, which reads as "no results" rather than "wrong page".
    await waitFor(() => {
      expect(mockedListBacklinks).toHaveBeenLastCalledWith(
        'p-1',
        expect.objectContaining({ offset: 0, sort: 'toxicity' }),
        expect.anything(),
      )
    })
  })

  it('marks an unassessed link as unassessed rather than clean', async () => {
    render(<BacklinkInventoryPanel projectId="p-1" />)

    expect(await screen.findByText(/not assessed/i)).toBeInTheDocument()
  })

  it('shows a toxicity band with its score when one exists', async () => {
    mockedListBacklinks.mockResolvedValue({
      total: 1,
      limit: 25,
      offset: 0,
      items: [link({ toxicity_band: 'high', toxicity_score: 71 })],
    })
    render(<BacklinkInventoryPanel projectId="p-1" />)

    expect(await screen.findByText(/high 71/i)).toBeInTheDocument()
  })

  it('surfaces a load failure instead of rendering an empty table', async () => {
    mockedListBacklinks.mockRejectedValue(new Error('Backlinks are unavailable.'))
    render(<BacklinkInventoryPanel projectId="p-1" />)

    expect(
      await screen.findByRole('heading', { name: /could not be loaded/i }),
    ).toBeInTheDocument()
  })
})
