import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type {
  SearchConsoleConnections,
  SearchConsolePerformance,
  SearchConsoleProperties,
} from '@/lib/contracts'
import { axeCheck } from './a11y'

const mockedListConnections = vi.hoisted(() => vi.fn())
const mockedListProperties = vi.hoisted(() => vi.fn())
const mockedGetPerformance = vi.hoisted(() => vi.fn())

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => '/site-audit/project-1',
}))
vi.mock('@/lib/api', () => ({
  listSearchConsoleConnections: mockedListConnections,
  listSearchConsoleProperties: mockedListProperties,
  startSearchConsoleConnect: vi.fn(),
  linkSearchConsoleProperty: vi.fn(),
  unlinkSearchConsoleProperty: vi.fn(),
  getSearchConsolePerformance: mockedGetPerformance,
}))
vi.mock('@/lib/navigation', () => ({ redirectToExternal: vi.fn() }))

import SearchConsoleConnectionCard from '@/components/site-audit/search-console/SearchConsoleConnectionCard'

const CONNECTION = {
  id: 'conn-1',
  google_account_email: 'owner@example.test',
  status: 'active',
  scopes: ['openid'],
  created_at: '2026-08-06T09:00:00Z',
  updated_at: '2026-08-06T09:00:00Z',
  selected_for_project: false,
  selected_site_url: null,
}

const NO_PROPERTY: SearchConsoleConnections = {
  project_status: 'no_property_selected',
  connections: [CONNECTION],
}

const CONNECTED: SearchConsoleConnections = {
  project_status: 'connected',
  connections: [
    { ...CONNECTION, selected_for_project: true, selected_site_url: 'sc-domain:example.com' },
  ],
}

const PROPERTIES: SearchConsoleProperties = {
  google_connection_id: 'conn-1',
  google_account_email: 'owner@example.test',
  properties: [
    {
      site_url: 'sc-domain:example.com',
      permission_level: 'siteOwner',
      property_type: 'domain',
      matches_project_domain: true,
      currently_selected: false,
    },
  ],
}

const PERFORMANCE: SearchConsolePerformance = {
  site_url: 'sc-domain:example.com',
  start_date: '2026-07-07',
  end_date: '2026-08-03',
  data_state: 'ok',
  summary: { clicks: 12, impressions: 340, ctr: 0.035, position: 9.1 },
  top_queries: [],
  top_pages: [],
}

function renderCard() {
  return render(<SearchConsoleConnectionCard projectId="project-1" enabled />)
}

describe('SearchConsoleConnectionCard accessibility', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.history.replaceState({}, '', '/site-audit/project-1')
    mockedListProperties.mockResolvedValue(PROPERTIES)
    mockedGetPerformance.mockResolvedValue(PERFORMANCE)
  })

  it('has no axe violations when nothing is connected', async () => {
    mockedListConnections.mockResolvedValue({
      project_status: 'no_connection',
      connections: [],
    })
    const { container } = renderCard()
    await screen.findByRole('button', { name: 'Connect Google Search Console' })

    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('has no axe violations with an account but no property', async () => {
    mockedListConnections.mockResolvedValue(NO_PROPERTY)
    const { container } = renderCard()
    await screen.findByText('owner@example.test')

    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('has no axe violations with a linked property and its metrics', async () => {
    mockedListConnections.mockResolvedValue(CONNECTED)
    const { container } = renderCard()
    await screen.findByText('3.5%')

    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('has no axe violations in the property picker', async () => {
    mockedListConnections.mockResolvedValue(NO_PROPERTY)
    const { container } = renderCard()
    await userEvent.click(await screen.findByRole('button', { name: 'Choose property' }))
    await screen.findByRole('dialog')

    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('has no axe violations while confirming a disconnect', async () => {
    mockedListConnections.mockResolvedValue(CONNECTED)
    const { container } = renderCard()
    await userEvent.click(
      await screen.findByRole('button', { name: 'Disconnect property' }),
    )

    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('has no axe violations in the error state', async () => {
    mockedListConnections.mockRejectedValue(new Error('Connections could not load.'))
    const { container } = renderCard()
    await screen.findByRole('alert')

    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('moves focus into the dialog and restores it on close', async () => {
    mockedListConnections.mockResolvedValue(NO_PROPERTY)
    renderCard()
    const opener = await screen.findByRole('button', { name: 'Choose property' })

    await userEvent.click(opener)
    const dialog = await screen.findByRole('dialog')
    expect(dialog.contains(document.activeElement)).toBe(true)

    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    expect(document.activeElement).toBe(opener)
  })

  it('locks body scroll only while the dialog is open', async () => {
    mockedListConnections.mockResolvedValue(NO_PROPERTY)
    renderCard()

    await userEvent.click(await screen.findByRole('button', { name: 'Choose property' }))
    const dialog = await screen.findByRole('dialog')
    expect(document.body.style.overflow).toBe('hidden')

    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    expect(document.body.style.overflow).not.toBe('hidden')
  })

  it('states every status in words, not only in colour', async () => {
    mockedListConnections.mockResolvedValue({
      project_status: 'reauth_required',
      connections: [
        { ...CONNECTION, status: 'reauth_required', selected_for_project: true },
      ],
    })
    renderCard()

    // The badge is tinted red; the words carry the same information.
    expect(await screen.findByText('Reconnect needed')).toBeInTheDocument()
    expect(screen.getByText('Needs reconnecting')).toBeInTheDocument()
  })
})
