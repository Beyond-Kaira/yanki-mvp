import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SessionsSection from '@/components/settings/SessionsSection'

const fetchSessions = vi.fn()
const revokeSession = vi.fn()
const revokeAllSessions = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    fetchSessions: (...args: unknown[]) => fetchSessions(...args),
    revokeSession: (...args: unknown[]) => revokeSession(...args),
    revokeAllSessions: (...args: unknown[]) => revokeAllSessions(...args),
  }
})

function session(overrides: Record<string, unknown> = {}) {
  return {
    id: 's1',
    created_at: '2026-08-01T10:00:00Z',
    last_active_at: '2026-08-05T12:00:00Z',
    expires_at: '2026-09-01T10:00:00Z',
    current: false,
    ...overrides,
  }
}

describe('SessionsSection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    revokeSession.mockResolvedValue(undefined)
  })

  it('lists sessions, marks the current one, and offers Revoke only for the others', async () => {
    fetchSessions.mockResolvedValue({
      sessions: [session({ id: 'cur', current: true }), session({ id: 'other' })],
    })

    render(<SessionsSection />)

    expect(await screen.findByText('This device')).toBeVisible()
    expect(screen.getByText('Current')).toBeVisible()
    // The current session has no Revoke button — only the other one does.
    expect(screen.getAllByRole('button', { name: 'Revoke' })).toHaveLength(1)
  })

  it('revokes a single session by its id and reloads the list', async () => {
    fetchSessions
      .mockResolvedValueOnce({
        sessions: [session({ id: 'cur', current: true }), session({ id: 'other' })],
      })
      .mockResolvedValue({ sessions: [session({ id: 'cur', current: true })] })

    render(<SessionsSection />)
    await screen.findByText('This device')

    await userEvent.click(screen.getByRole('button', { name: 'Revoke' }))

    expect(revokeSession).toHaveBeenCalledWith('other')
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Revoke' })).not.toBeInTheDocument(),
    )
  })

  it('signs out other sessions only after an explicit confirmation', async () => {
    fetchSessions
      .mockResolvedValueOnce({
        sessions: [
          session({ id: 'cur', current: true }),
          session({ id: 'o1' }),
          session({ id: 'o2' }),
        ],
      })
      .mockResolvedValue({ sessions: [session({ id: 'cur', current: true })] })
    revokeAllSessions.mockResolvedValue({ revoked: 2, kept_current: true })

    render(<SessionsSection />)
    await screen.findByText('This device')

    // First click only arms the confirmation — nothing is revoked yet.
    await userEvent.click(screen.getByRole('button', { name: /sign out other sessions/i }))
    expect(revokeAllSessions).not.toHaveBeenCalled()
    expect(screen.getByText(/sign out 2 other sessions\?/i)).toBeVisible()

    await userEvent.click(screen.getByRole('button', { name: 'Confirm' }))

    expect(revokeAllSessions).toHaveBeenCalledTimes(1)
    expect(await screen.findByText(/signed out 2 other sessions/i)).toBeVisible()
  })

  it('does not offer a sign-out-others control when the current session is the only one', async () => {
    fetchSessions.mockResolvedValue({
      sessions: [session({ id: 'cur', current: true })],
    })

    render(<SessionsSection />)
    await screen.findByText('This device')

    expect(
      screen.queryByRole('button', { name: /sign out other sessions/i }),
    ).not.toBeInTheDocument()
  })
})
