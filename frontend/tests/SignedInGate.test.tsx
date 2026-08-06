import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SignedInGate from '@/components/SignedInGate'

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

function renderGate(hinted: boolean) {
  return render(
    <SignedInGate hinted={hinted}>
      <p>the pitch</p>
    </SignedInGate>,
  )
}

describe('SignedInGate', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('paints the pitch immediately for a browser with no session hint', () => {
    authState = { status: 'loading' }
    renderGate(false)

    expect(screen.getByText('the pitch')).toBeVisible()
    expect(replace).not.toHaveBeenCalled()
  })

  it('withholds the pitch while a hinted browser resolves its session', () => {
    authState = { status: 'loading' }
    renderGate(true)

    expect(screen.queryByText('the pitch')).not.toBeInTheDocument()
    expect(replace).not.toHaveBeenCalled()
  })

  it('falls back to the pitch when a stale hint turns out to be anonymous', () => {
    authState = { status: 'anonymous' }
    renderGate(true)

    expect(screen.getByText('the pitch')).toBeVisible()
    expect(replace).not.toHaveBeenCalled()
  })

  it('never shows the pitch to someone signed in', async () => {
    authState = { status: 'authenticated' }
    renderGate(true)

    expect(screen.queryByText('the pitch')).not.toBeInTheDocument()
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/dashboard'))
  })

  it('redirects a signed-in visitor even when the hint was missing', async () => {
    authState = { status: 'authenticated' }
    renderGate(false)

    expect(screen.queryByText('the pitch')).not.toBeInTheDocument()
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/dashboard'))
  })

  it('honours an explicit destination', async () => {
    authState = { status: 'authenticated' }
    render(
      <SignedInGate hinted to="/settings">
        <p>the pitch</p>
      </SignedInGate>,
    )

    await waitFor(() => expect(replace).toHaveBeenCalledWith('/settings'))
  })
})
