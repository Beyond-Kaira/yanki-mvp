import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import OrgSwitcher from '@/components/shell/OrgSwitcher'

const push = vi.fn()
const switchOrg = vi.fn().mockResolvedValue(undefined)

function org(id: string, name: string, role: string) {
  return { id, name, slug: name.toLowerCase(), kind: 'company', status: 'active', role }
}

function userWith(orgs: ReturnType<typeof org>[], activeId: string | null) {
  return {
    email: 'contractor@example.com',
    organization: activeId ? orgs.find((o) => o.id === activeId) ?? null : null,
    organizations: orgs,
  }
}

let authValue: { user: ReturnType<typeof userWith>; switchOrg: typeof switchOrg }

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
}))

vi.mock('@/components/AuthProvider', () => ({
  useAuth: () => authValue,
}))

describe('OrgSwitcher', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders nothing for a single-org user — a solo account gets no new chrome', () => {
    authValue = { user: userWith([org('a', 'Acme', 'owner')], 'a'), switchOrg }
    const { container } = render(<OrgSwitcher />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing when the user has no organizations', () => {
    authValue = { user: userWith([], null), switchOrg }
    const { container } = render(<OrgSwitcher />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows the active org and lists every membership when opened', async () => {
    const orgs = [org('a', 'Acme', 'owner'), org('b', 'Beta LLC', 'admin')]
    authValue = { user: userWith(orgs, 'a'), switchOrg }
    render(<OrgSwitcher />)

    const trigger = screen.getByRole('button', { name: /switch organization/i })
    expect(trigger).toHaveTextContent('Acme')

    await userEvent.click(trigger)
    const listbox = screen.getByRole('listbox')
    expect(within(listbox).getByText('Acme')).toBeVisible()
    expect(within(listbox).getByText('Beta LLC')).toBeVisible()
    expect(within(listbox).getByText('Admin')).toBeVisible()
  })

  it('switches scope and lands on the dashboard when another org is chosen', async () => {
    const orgs = [org('a', 'Acme', 'owner'), org('b', 'Beta LLC', 'admin')]
    authValue = { user: userWith(orgs, 'a'), switchOrg }
    render(<OrgSwitcher />)

    await userEvent.click(screen.getByRole('button', { name: /switch organization/i }))
    await userEvent.click(within(screen.getByRole('listbox')).getByText('Beta LLC'))

    expect(switchOrg).toHaveBeenCalledWith('b')
    await waitFor(() => expect(push).toHaveBeenCalledWith('/dashboard'))
  })

  it('does nothing when the already-active org is chosen again', async () => {
    const orgs = [org('a', 'Acme', 'owner'), org('b', 'Beta LLC', 'admin')]
    authValue = { user: userWith(orgs, 'a'), switchOrg }
    render(<OrgSwitcher />)

    await userEvent.click(screen.getByRole('button', { name: /switch organization/i }))
    await userEvent.click(within(screen.getByRole('listbox')).getByText('Acme'))

    expect(switchOrg).not.toHaveBeenCalled()
    expect(push).not.toHaveBeenCalled()
  })
})
