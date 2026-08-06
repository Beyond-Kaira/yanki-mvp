import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type {
  SearchConsoleConnections,
  SearchConsolePerformance,
  SearchConsoleProperties,
} from '@/lib/contracts'

const mockedListConnections = vi.hoisted(() => vi.fn())
const mockedListProperties = vi.hoisted(() => vi.fn())
const mockedStartConnect = vi.hoisted(() => vi.fn())
const mockedLinkProperty = vi.hoisted(() => vi.fn())
const mockedUnlinkProperty = vi.hoisted(() => vi.fn())
const mockedGetPerformance = vi.hoisted(() => vi.fn())
const mockedRedirect = vi.hoisted(() => vi.fn())
const mockedReplace = vi.hoisted(() => vi.fn())

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: mockedReplace }),
  usePathname: () => '/site-audit/project-1',
}))
vi.mock('@/lib/api', () => ({
  listSearchConsoleConnections: mockedListConnections,
  listSearchConsoleProperties: mockedListProperties,
  startSearchConsoleConnect: mockedStartConnect,
  linkSearchConsoleProperty: mockedLinkProperty,
  unlinkSearchConsoleProperty: mockedUnlinkProperty,
  getSearchConsolePerformance: mockedGetPerformance,
}))
// jsdom does not implement navigation and `window.location` is not reliably
// patchable, so the one line that leaves the app lives behind this seam.
vi.mock('@/lib/navigation', () => ({ redirectToExternal: mockedRedirect }))

import SearchConsoleConnectionCard from '@/components/site-audit/search-console/SearchConsoleConnectionCard'

const NOT_CONNECTED: SearchConsoleConnections = {
  project_status: 'no_connection',
  connections: [],
}

const CONNECTION = {
  id: 'conn-1',
  google_account_email: 'owner@example.test',
  status: 'active',
  scopes: ['openid', 'email', 'https://www.googleapis.com/auth/webmasters.readonly'],
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
    {
      site_url: 'https://shop.example.com/',
      permission_level: 'siteFullUser',
      property_type: 'url_prefix',
      matches_project_domain: false,
      currently_selected: false,
    },
  ],
}

const PERFORMANCE: SearchConsolePerformance = {
  site_url: 'sc-domain:example.com',
  start_date: '2026-07-07',
  end_date: '2026-08-03',
  data_state: 'ok',
  summary: { clicks: 1234, impressions: 45678, ctr: 0.027, position: 12.34 },
  top_queries: [],
  top_pages: [],
}

function renderCard() {
  return render(<SearchConsoleConnectionCard projectId="project-1" enabled />)
}

describe('SearchConsoleConnectionCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.history.replaceState({}, '', '/site-audit/project-1')
    mockedListConnections.mockResolvedValue(NOT_CONNECTED)
    mockedGetPerformance.mockResolvedValue(PERFORMANCE)
    mockedListProperties.mockResolvedValue(PROPERTIES)
  })

  // ---------------------------------------------------------------- connect

  it('offers a connect button when no Google account is linked', async () => {
    renderCard()

    expect(
      await screen.findByRole('button', { name: 'Connect Google Search Console' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Not connected')).toBeInTheDocument()
  })

  it('sends the browser to the authorization url the backend returned', async () => {
    mockedStartConnect.mockResolvedValue({
      authorization_url: 'https://accounts.google.com/o/oauth2/v2/auth?state=abc',
    })
    renderCard()

    await userEvent.click(
      await screen.findByRole('button', { name: 'Connect Google Search Console' }),
    )

    await waitFor(() => {
      expect(mockedRedirect).toHaveBeenCalledWith(
        'https://accounts.google.com/o/oauth2/v2/auth?state=abc',
      )
    })
    // The frontend never assembles this URL itself.
    expect(mockedStartConnect).toHaveBeenCalledWith('project-1')
  })

  it('surfaces a failure to start the connection', async () => {
    mockedStartConnect.mockRejectedValue(new Error('Search Console is not available.'))
    renderCard()

    await userEvent.click(
      await screen.findByRole('button', { name: 'Connect Google Search Console' }),
    )

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Search Console is not available.',
    )
    expect(mockedRedirect).not.toHaveBeenCalled()
  })

  it('reports a failure to load connections with a retry', async () => {
    mockedListConnections.mockRejectedValueOnce(new Error('Google connections failed.'))
    renderCard()

    expect(await screen.findByRole('alert')).toHaveTextContent('Google connections failed.')

    mockedListConnections.mockResolvedValue(NOT_CONNECTED)
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))

    expect(
      await screen.findByRole('button', { name: 'Connect Google Search Console' }),
    ).toBeInTheDocument()
  })

  // ------------------------------------------------------------- account list

  it('lists every connected Google account and offers to add another', async () => {
    mockedListConnections.mockResolvedValue({
      project_status: 'no_property_selected',
      connections: [
        CONNECTION,
        { ...CONNECTION, id: 'conn-2', google_account_email: 'second@example.test' },
      ],
    })
    renderCard()

    expect(await screen.findByText('owner@example.test')).toBeInTheDocument()
    expect(screen.getByText('second@example.test')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Add another Google account' }),
    ).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Choose property' })).toHaveLength(2)
  })

  it('shows a reconnect path when the grant has expired', async () => {
    mockedListConnections.mockResolvedValue({
      project_status: 'reauth_required',
      connections: [
        {
          ...CONNECTION,
          status: 'reauth_required',
          selected_for_project: true,
          selected_site_url: 'sc-domain:example.com',
        },
      ],
    })
    renderCard()

    expect(await screen.findByText('Reconnect needed')).toBeInTheDocument()
    expect(screen.getByText('Needs reconnecting')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Reconnect this account' }),
    ).toBeInTheDocument()
    // A dead grant must not be presented as live numbers.
    expect(mockedGetPerformance).not.toHaveBeenCalled()
  })

  it('never renders a token, scope or account identifier', async () => {
    mockedListConnections.mockResolvedValue(CONNECTED)
    const { container } = renderCard()
    await screen.findByText('owner@example.test')

    const text = container.textContent ?? ''
    expect(text).not.toMatch(/webmasters\.readonly/)
    expect(text).not.toMatch(/openid/)
    expect(text).not.toMatch(/refresh_token/i)
    expect(text).not.toMatch(/ciphertext/i)
  })

  // --------------------------------------------------------- property picker

  it('opens the property picker and marks the recommended property', async () => {
    mockedListConnections.mockResolvedValue(NO_PROPERTY)
    renderCard()

    await userEvent.click(await screen.findByRole('button', { name: 'Choose property' }))

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByRole('heading', { name: 'Choose a property' })).toBeVisible()
    expect(within(dialog).getByText('Recommended')).toBeInTheDocument()

    // Recommended, not chosen: nothing is preselected.
    const radios = within(dialog).getAllByRole('radio')
    expect(radios.every((radio) => !(radio as HTMLInputElement).checked)).toBe(true)
    expect(within(dialog).getByRole('button', { name: 'Connect property' })).toBeDisabled()
  })

  it('links the chosen property and reloads', async () => {
    mockedListConnections.mockResolvedValueOnce(NO_PROPERTY).mockResolvedValue(CONNECTED)
    mockedLinkProperty.mockResolvedValue({})
    renderCard()

    await userEvent.click(await screen.findByRole('button', { name: 'Choose property' }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.click(within(dialog).getByRole('radio', { name: /sc-domain:example\.com/ }))
    await userEvent.click(within(dialog).getByRole('button', { name: 'Connect property' }))

    await waitFor(() => {
      expect(mockedLinkProperty).toHaveBeenCalledWith('project-1', {
        google_connection_id: 'conn-1',
        site_url: 'sc-domain:example.com',
      })
    })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Connected to sc-domain:example.com.',
    )
    await waitFor(() => expect(mockedGetPerformance).toHaveBeenCalled())
  })

  it('keeps the picker open and explains a rejected property', async () => {
    mockedListConnections.mockResolvedValue(NO_PROPERTY)
    mockedLinkProperty.mockRejectedValue(
      new Error('That property is not available to this Google account. Pick another one.'),
    )
    renderCard()

    await userEvent.click(await screen.findByRole('button', { name: 'Choose property' }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.click(within(dialog).getByRole('radio', { name: /sc-domain:example\.com/ }))
    await userEvent.click(within(dialog).getByRole('button', { name: 'Connect property' }))

    expect(await within(dialog).findByRole('alert')).toHaveTextContent(
      'That property is not available to this Google account.',
    )
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('closes the picker on Escape', async () => {
    mockedListConnections.mockResolvedValue(NO_PROPERTY)
    renderCard()

    await userEvent.click(await screen.findByRole('button', { name: 'Choose property' }))
    await screen.findByRole('dialog')

    await userEvent.keyboard('{Escape}')

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('explains an account with no verified properties', async () => {
    mockedListConnections.mockResolvedValue(NO_PROPERTY)
    mockedListProperties.mockResolvedValue({ ...PROPERTIES, properties: [] })
    renderCard()

    await userEvent.click(await screen.findByRole('button', { name: 'Choose property' }))

    const dialog = await screen.findByRole('dialog')
    expect(
      await within(dialog).findByRole('heading', { name: 'No properties available' }),
    ).toBeInTheDocument()
  })

  it('offers change property once one is linked', async () => {
    mockedListConnections.mockResolvedValue(CONNECTED)
    renderCard()

    expect(
      await screen.findByRole('button', { name: 'Change property' }),
    ).toBeInTheDocument()
    expect(screen.getByText('sc-domain:example.com')).toBeInTheDocument()
  })

  // ----------------------------------------------------------- disconnecting

  it('asks for confirmation before disconnecting and says the account stays', async () => {
    mockedListConnections.mockResolvedValue(CONNECTED)
    renderCard()

    await userEvent.click(
      await screen.findByRole('button', { name: 'Disconnect property' }),
    )

    const confirm = screen.getByRole('group', {
      name: 'Confirm disconnecting the property',
    })
    expect(confirm).toHaveTextContent('The Google account stays connected')
    expect(mockedUnlinkProperty).not.toHaveBeenCalled()
  })

  it('can back out of disconnecting', async () => {
    mockedListConnections.mockResolvedValue(CONNECTED)
    renderCard()

    await userEvent.click(
      await screen.findByRole('button', { name: 'Disconnect property' }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Keep it connected' }))

    expect(
      screen.queryByRole('group', { name: 'Confirm disconnecting the property' }),
    ).not.toBeInTheDocument()
    expect(mockedUnlinkProperty).not.toHaveBeenCalled()
  })

  it('disconnects and reloads the connection state', async () => {
    mockedListConnections.mockResolvedValueOnce(CONNECTED).mockResolvedValue(NO_PROPERTY)
    mockedUnlinkProperty.mockResolvedValue(undefined)
    renderCard()

    await userEvent.click(
      await screen.findByRole('button', { name: 'Disconnect property' }),
    )
    const confirm = screen.getByRole('group', {
      name: 'Confirm disconnecting the property',
    })
    await userEvent.click(
      within(confirm).getByRole('button', { name: 'Disconnect property' }),
    )

    await waitFor(() => expect(mockedUnlinkProperty).toHaveBeenCalledWith('project-1'))
    expect(await screen.findByRole('status')).toHaveTextContent(
      'The Google account is still connected.',
    )
    await waitFor(() => expect(mockedListConnections).toHaveBeenCalledTimes(2))
  })

  // -------------------------------------------------------- callback returns

  it('announces a successful return from Google and clears the query', async () => {
    window.history.replaceState({}, '', '/site-audit/project-1?gsc=connected')
    mockedListConnections.mockResolvedValue(NO_PROPERTY)
    renderCard()

    expect(await screen.findByRole('status')).toHaveTextContent('Google account connected')
    expect(mockedReplace).toHaveBeenCalledWith('/site-audit/project-1')
  })

  it.each([
    ['access_denied', 'You cancelled the Google sign-in'],
    ['invalid_state', 'no longer valid'],
    ['expired_state', 'timed out'],
    ['provider_error', 'Google could not complete the connection'],
    ['invalid_identity', 'could not verify that account'],
    ['missing_refresh_token', 'did not grant lasting access'],
  ])('maps the %s callback reason to a safe message', async (reason, expected) => {
    window.history.replaceState({}, '', `/site-audit/project-1?gsc=error&reason=${reason}`)
    renderCard()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(expected)
    expect(alert).not.toHaveTextContent(reason)
  })

  it('never renders an unrecognised reason from the url', async () => {
    window.history.replaceState(
      {},
      '',
      '/site-audit/project-1?gsc=error&reason=%3Cscript%3Ealert(1)%3C/script%3E',
    )
    renderCard()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('The Google connection did not complete.')
    expect(alert).not.toHaveTextContent('script')
  })

  // ------------------------------------------------------------- performance

  it('shows the performance summary once a property is linked', async () => {
    mockedListConnections.mockResolvedValue(CONNECTED)
    renderCard()

    expect(await screen.findByText('1,234')).toBeInTheDocument()
    expect(screen.getByText('45,678')).toBeInTheDocument()
    expect(screen.getByText('2.7%')).toBeInTheDocument()
    expect(screen.getByText('12.3')).toBeInTheDocument()
    expect(screen.getByText('2026-07-07 to 2026-08-03')).toBeInTheDocument()
  })

  it('says so plainly when the property has no data for the period', async () => {
    mockedListConnections.mockResolvedValue(CONNECTED)
    mockedGetPerformance.mockResolvedValue({
      ...PERFORMANCE,
      data_state: 'no_data',
      summary: { clicks: 0, impressions: 0, ctr: null, position: null },
    })
    renderCard()

    expect(
      await screen.findByText('No Search Console data for this period.'),
    ).toBeInTheDocument()
  })

  it('draws a null ctr and position as an em dash rather than zero', async () => {
    mockedListConnections.mockResolvedValue(CONNECTED)
    mockedGetPerformance.mockResolvedValue({
      ...PERFORMANCE,
      summary: { clicks: 5, impressions: 0, ctr: null, position: null },
    })
    renderCard()

    await screen.findByText('5')
    expect(screen.getAllByText('—')).toHaveLength(2)
    expect(screen.queryByText('0.0%')).not.toBeInTheDocument()
    expect(screen.queryByText('0.0')).not.toBeInTheDocument()
  })

  it('keeps the connection visible when performance fails', async () => {
    mockedListConnections.mockResolvedValue(CONNECTED)
    mockedGetPerformance.mockRejectedValue(
      new Error('Google is rate limiting these requests. Try again in a minute.'),
    )
    renderCard()

    expect(await screen.findByRole('alert')).toHaveTextContent('rate limiting')
    // The card that explains the outage must survive the outage.
    expect(screen.getByText('owner@example.test')).toBeInTheDocument()
    expect(screen.getByText('Connected')).toBeInTheDocument()
  })

  it('does not fetch performance when no property is linked', async () => {
    mockedListConnections.mockResolvedValue(NO_PROPERTY)
    renderCard()

    await screen.findByText('owner@example.test')
    expect(mockedGetPerformance).not.toHaveBeenCalled()
  })

  // ------------------------------------------------- the feature being off
  //
  // GSC_ENABLED=false makes the backend 404 the whole surface, so that a
  // disabled feature is indistinguishable from one that does not exist. These
  // pin both halves of honouring that: render nothing, and ask once.

  it('renders nothing at all when the module is switched off', async () => {
    const notFound = Object.assign(new Error('Search Console is not available.'), {
      status: 404,
    })
    mockedListConnections.mockRejectedValue(notFound)
    const { container } = renderCard()

    await waitFor(() => expect(mockedListConnections).toHaveBeenCalled())
    await waitFor(() => expect(container).toBeEmptyDOMElement())
    // No red box announcing the feature we just chose to hide.
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByText(/not available/i)).not.toBeInTheDocument()
  })

  it('asks exactly once when the module is switched off', async () => {
    const notFound = Object.assign(new Error('nope'), { status: 404 })
    mockedListConnections.mockRejectedValue(notFound)
    renderCard()

    await waitFor(() => expect(mockedListConnections).toHaveBeenCalledTimes(1))
    // Long enough for a retry loop to show itself.
    await new Promise((resolve) => setTimeout(resolve, 150))
    expect(mockedListConnections).toHaveBeenCalledTimes(1)
    expect(mockedGetPerformance).not.toHaveBeenCalled()
  })

  it('does not refetch when the parent re-renders around it', async () => {
    // The detail page polls its audit every 2.5s while a crawl runs, which
    // re-renders this card. A dependency that changed identity per render would
    // turn that poll into a Search Console request storm.
    const notFound = Object.assign(new Error('nope'), { status: 404 })
    mockedListConnections.mockRejectedValue(notFound)
    const { rerender } = renderCard()

    await waitFor(() => expect(mockedListConnections).toHaveBeenCalledTimes(1))
    for (let i = 0; i < 5; i += 1) {
      rerender(<SearchConsoleConnectionCard projectId="project-1" enabled />)
    }
    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(mockedListConnections).toHaveBeenCalledTimes(1)
  })

  it('does not refetch on a parent re-render once loaded either', async () => {
    mockedListConnections.mockResolvedValue(CONNECTED)
    const { rerender } = renderCard()
    await screen.findByText('owner@example.test')

    for (let i = 0; i < 5; i += 1) {
      rerender(<SearchConsoleConnectionCard projectId="project-1" enabled />)
    }
    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(mockedListConnections).toHaveBeenCalledTimes(1)
    expect(mockedGetPerformance).toHaveBeenCalledTimes(1)
  })

  it('still allows an explicit retry after a real error', async () => {
    mockedListConnections.mockRejectedValueOnce(new Error('Connections failed.'))
    renderCard()

    await screen.findByRole('alert')
    expect(mockedListConnections).toHaveBeenCalledTimes(1)

    mockedListConnections.mockResolvedValue(NOT_CONNECTED)
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))

    await waitFor(() => expect(mockedListConnections).toHaveBeenCalledTimes(2))
  })

  it('makes one request per mount, not one per effect pass', async () => {
    mockedListConnections.mockResolvedValue(NOT_CONNECTED)
    renderCard()

    await screen.findByRole('button', { name: 'Connect Google Search Console' })
    await new Promise((resolve) => setTimeout(resolve, 100))

    expect(mockedListConnections).toHaveBeenCalledTimes(1)
  })
})
