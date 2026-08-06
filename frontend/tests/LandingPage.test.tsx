import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LandingPage from '@/app/page'

const replace = vi.fn()
let authState: { status: 'loading' | 'authenticated' | 'anonymous' } = {
  status: 'anonymous',
}
let hinted = false

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
}))

vi.mock('@/components/AuthProvider', () => ({
  useAuth: () => authState,
}))

vi.mock('next/headers', () => ({
  cookies: async () => ({ has: () => hinted }),
}))

beforeEach(() => {
  vi.clearAllMocks()
  authState = { status: 'anonymous' }
  hinted = false
})

async function renderLanding() {
  return render(await LandingPage())
}

/**
 * The operator's complaint was that a fresh session "navigates directly to the
 * search page". These assert the opposite property directly: `/` explains the
 * product and offers a way in, and does NOT render the signed-in application.
 */
describe('Landing page', () => {
  it('explains what the product does', async () => {
    await renderLanding()

    expect(
      screen.getByRole('heading', { level: 1, name: /what AI answers say about your brand/i }),
    ).toBeVisible()
  })

  it('offers both a way in and a way to try it', async () => {
    await renderLanding()

    expect(screen.getAllByRole('link', { name: /create an account/i }).length).toBeGreaterThan(0)
    expect(screen.getByRole('link', { name: /log in/i })).toHaveAttribute('href', '/login')
    expect(screen.getByRole('link', { name: /free checker/i })).toHaveAttribute(
      'href',
      '/checker',
    )
  })

  it('does not render the signed-in application', async () => {
    // The regression: `/` used to mount the product shell and a URL form, so a
    // first-time visitor saw a signed-out app instead of an explanation.
    await renderLanding()

    expect(screen.queryByRole('navigation', { name: /product navigation/i })).toBeNull()
    expect(screen.queryByLabelText(/url/i)).toBeNull()
    expect(screen.queryByRole('button', { name: /run analysis/i })).toBeNull()
  })

  it('sends a signed-in visitor to the dashboard', async () => {
    authState = { status: 'authenticated' }
    await renderLanding()

    await waitFor(() => expect(replace).toHaveBeenCalledWith('/dashboard'))
  })

  it('paints the pitch with no delay for a browser that has never signed in', async () => {
    authState = { status: 'loading' }
    await renderLanding()

    expect(screen.getByRole('heading', { level: 1 })).toBeVisible()
    expect(screen.getAllByRole('link', { name: /create an account/i }).length).toBeGreaterThan(0)
    expect(replace).not.toHaveBeenCalled()
  })

  it('shows a hinted browser nothing rather than a flash of the pitch', async () => {
    hinted = true
    authState = { status: 'loading' }
    await renderLanding()

    expect(screen.queryByRole('heading', { level: 1 })).toBeNull()
    expect(screen.queryByRole('link', { name: /create an account/i })).toBeNull()
  })

  it('recovers the pitch when a hint outlives its session', async () => {
    hinted = true
    authState = { status: 'anonymous' }
    await renderLanding()

    expect(screen.getByRole('heading', { level: 1 })).toBeVisible()
    expect(replace).not.toHaveBeenCalled()
  })

  it('leaves an anonymous visitor where they are', async () => {
    await renderLanding()

    expect(replace).not.toHaveBeenCalled()
  })

  it('scales its headline down on small screens', async () => {
    const { container } = await renderLanding()
    const h1 = container.querySelector('h1')

    // A 48px headline on a 343px line is the classic mobile overflow.
    expect(h1?.className).toMatch(/text-3xl/)
    expect(h1?.className).toMatch(/sm:text-5xl/)
  })
})
