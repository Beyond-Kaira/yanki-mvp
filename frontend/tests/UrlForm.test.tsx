import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const push = vi.fn()

let pathname = '/'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  usePathname: () => pathname,
}))

vi.mock('@/lib/api', () => ({
  createAnalysis: vi.fn(),
}))

import UrlForm from '@/components/UrlForm'
import { createAnalysis } from '@/lib/api'

const mockedCreate = vi.mocked(createAnalysis)

describe('UrlForm', () => {
  beforeEach(() => {
    pathname = '/'
    push.mockReset()
    mockedCreate.mockReset()
  })

  it('shows an inline error and does not POST for an invalid URL', async () => {
    const user = userEvent.setup()
    render(<UrlForm />)

    await user.type(screen.getByLabelText(/url/i), 'not a url')
    await user.click(screen.getByRole('button', { name: /run analysis/i }))

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(mockedCreate).not.toHaveBeenCalled()
  })

  it('posts and disables the button for a valid URL', async () => {
    const user = userEvent.setup()
    // Never resolves, so the form stays in its submitting (disabled) state.
    mockedCreate.mockReturnValue(new Promise<{ id: string }>(() => {}))
    render(<UrlForm />)

    await user.type(screen.getByLabelText(/url/i), 'https://example.com')
    await user.click(screen.getByRole('button', { name: /run analysis/i }))

    expect(mockedCreate).toHaveBeenCalledWith('https://example.com', { mode: 'quick' })
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /run analysis/i })).toBeDisabled(),
    )
  })

  it('sends guided runs from the dashboard to the AI Visibility review wizard', async () => {
    const user = userEvent.setup()
    pathname = '/dashboard'
    mockedCreate.mockResolvedValue({ id: 'run-123' })
    render(<UrlForm />)

    await user.click(screen.getByRole('radio', { name: /guided/i }))
    await user.type(screen.getByLabelText(/url/i), 'https://example.com')
    await user.click(screen.getByRole('button', { name: /start guided run/i }))

    expect(mockedCreate).toHaveBeenCalledWith('https://example.com', { mode: 'guided' })
    expect(push).toHaveBeenCalledWith('/ai-visibility?analysis=run-123')
  })
})
