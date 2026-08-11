import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import RouteGuard from '@/components/RouteGuard'

const replace = vi.fn()
let pathname = '/dashboard'
let authState: { status: 'loading' | 'authenticated' | 'anonymous' } = {
  status: 'loading',
}

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
  usePathname: () => pathname,
}))

vi.mock('@/components/AuthProvider', () => ({
  useAuth: () => authState,
}))

function renderGuard() {
  return render(
    <RouteGuard>
      <p>product surface</p>
    </RouteGuard>,
  )
}

describe('RouteGuard on a protected route', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    pathname = '/dashboard'
    window.history.replaceState({}, '', '/dashboard')
  })

  it('does not mount the page while the session is still resolving', () => {
    authState = { status: 'loading' }
    renderGuard()

    expect(screen.queryByText('product surface')).not.toBeInTheDocument()
    expect(replace).not.toHaveBeenCalled()
  })

  it('does not mount the page for an anonymous visitor', () => {
    authState = { status: 'anonymous' }
    renderGuard()

    expect(screen.queryByText('product surface')).not.toBeInTheDocument()
  })

  it('sends an anonymous visitor to login carrying where they were headed', async () => {
    authState = { status: 'anonymous' }
    pathname = '/site-audit'
    window.history.replaceState({}, '', '/site-audit?project=abc')
    renderGuard()

    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith(
        `/login?next=${encodeURIComponent('/site-audit?project=abc')}`,
      ),
    )
  })

  it('mounts the page once authenticated', () => {
    authState = { status: 'authenticated' }
    renderGuard()

    expect(screen.getByText('product surface')).toBeVisible()
  })
})

describe('RouteGuard on a public route', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    pathname = '/checker'
    window.history.replaceState({}, '', '/checker')
  })

  it('renders straight through without waiting on the session', () => {
    authState = { status: 'loading' }
    renderGuard()

    expect(screen.getByText('product surface')).toBeVisible()
    expect(replace).not.toHaveBeenCalled()
  })

  it('never redirects an anonymous visitor away', () => {
    authState = { status: 'anonymous' }
    renderGuard()

    expect(screen.getByText('product surface')).toBeVisible()
    expect(replace).not.toHaveBeenCalled()
  })

  it('leaves a capability URL reachable', () => {
    authState = { status: 'anonymous' }
    pathname = '/analyses/abc123'
    renderGuard()

    expect(screen.getByText('product surface')).toBeVisible()
    expect(replace).not.toHaveBeenCalled()
  })
})
