import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AppLayout from '@/app/(app)/layout'

const replace = vi.fn()
let authState: { status: 'loading' | 'authenticated' | 'anonymous' } = {
  status: 'loading',
}

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
}))

vi.mock('@/components/AuthProvider', () => ({
  useAuth: () => authState,
}))

function renderLayout() {
  return render(
    <AppLayout>
      <p>product surface</p>
    </AppLayout>,
  )
}

/**
 * The regression this file exists for: every protected route is gated by this
 * one layout, so a page that stops being gated is a change HERE, not a change
 * spread across eight files nobody diffed together.
 *
 * `queryByText` rather than a visibility assertion — the requirement is that
 * protected children never MOUNT while the session is unresolved. Rendering
 * them hidden would still run their effects and fire their requests, and would
 * still flash on a slow connection.
 */
describe('(app) route group layout', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.history.replaceState({}, '', '/dashboard')
  })

  it('does not mount the product surface while the session is resolving', () => {
    authState = { status: 'loading' }
    renderLayout()

    expect(screen.queryByText('product surface')).not.toBeInTheDocument()
    expect(replace).not.toHaveBeenCalled()
  })

  it('does not mount the product surface for an anonymous visitor', () => {
    authState = { status: 'anonymous' }
    renderLayout()

    expect(screen.queryByText('product surface')).not.toBeInTheDocument()
  })

  it('sends an anonymous visitor to login carrying where they were headed', async () => {
    authState = { status: 'anonymous' }
    window.history.replaceState({}, '', '/site-audit?project=abc')
    renderLayout()

    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith(
        `/login?next=${encodeURIComponent('/site-audit?project=abc')}`,
      ),
    )
  })

  it('mounts the product surface once authenticated', () => {
    authState = { status: 'authenticated' }
    renderLayout()

    expect(screen.getByText('product surface')).toBeVisible()
  })
})
