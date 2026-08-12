import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LandingPage from '@/app/page'

let authState: { status: 'loading' | 'authenticated' | 'anonymous' } = {
  status: 'anonymous',
}

vi.mock('@/components/AuthProvider', () => ({
  useAuth: () => authState,
}))

/**
 * The operator's complaint was that a fresh session "navigates directly to the
 * search page". These assert the opposite property directly: `/` explains the
 * product and offers a way in, and does NOT render the signed-in application.
 *
 * Which way in depends on who is reading: a visitor is offered signup and the
 * free checker, somebody already signed in is offered their dashboard.
 */
describe('Landing page', () => {
  beforeEach(() => {
    authState = { status: 'anonymous' }
  })

  it('explains what the product does', () => {
    render(<LandingPage />)

    expect(
      screen.getByRole('heading', { level: 1, name: /what AI answers say about your brand/i }),
    ).toBeVisible()
  })

  it('does not render the signed-in application', () => {
    // The regression: `/` used to mount the product shell and a URL form, so a
    // first-time visitor saw a signed-out app instead of an explanation.
    render(<LandingPage />)

    expect(screen.queryByRole('navigation', { name: /product navigation/i })).toBeNull()
    expect(screen.queryByLabelText(/url/i)).toBeNull()
    expect(screen.queryByRole('button', { name: /run analysis/i })).toBeNull()
  })

  it('scales its headline down on small screens', () => {
    const { container } = render(<LandingPage />)
    const h1 = container.querySelector('h1')

    // A 48px headline on a 343px line is the classic mobile overflow.
    expect(h1?.className).toMatch(/text-3xl/)
    expect(h1?.className).toMatch(/sm:text-5xl/)
  })
})

describe('Landing page for a visitor', () => {
  beforeEach(() => {
    authState = { status: 'anonymous' }
  })

  it('offers a way in and a way to try it', () => {
    render(<LandingPage />)

    expect(screen.getAllByRole('link', { name: /create an account/i }).length).toBeGreaterThan(0)
    expect(screen.getByRole('link', { name: /log in/i })).toHaveAttribute('href', '/login')
    expect(screen.getByRole('link', { name: /free checker/i })).toHaveAttribute(
      'href',
      '/checker',
    )
  })

  it('closes with the signup pitch', () => {
    render(<LandingPage />)

    expect(screen.getByRole('heading', { name: /see your own numbers/i })).toBeVisible()
    expect(screen.getByRole('link', { name: /read the methodology/i })).toHaveAttribute(
      'href',
      '/methodology',
    )
  })

  it('does not offer the dashboard, which they cannot reach yet', () => {
    render(<LandingPage />)

    expect(screen.queryByRole('link', { name: /go to dashboard/i })).toBeNull()
  })
})

describe('Landing page for a signed-in reader', () => {
  beforeEach(() => {
    authState = { status: 'authenticated' }
  })

  it('offers the dashboard', () => {
    render(<LandingPage />)

    expect(screen.getByRole('link', { name: /go to dashboard/i })).toHaveAttribute(
      'href',
      '/dashboard',
    )
  })

  it('drops every invitation to sign up or log in', () => {
    render(<LandingPage />)

    expect(screen.queryByRole('link', { name: /create an account/i })).toBeNull()
    expect(screen.queryByRole('link', { name: /log in/i })).toBeNull()
    expect(screen.queryByRole('link', { name: /free checker/i })).toBeNull()
    expect(screen.queryByRole('heading', { name: /see your own numbers/i })).toBeNull()
  })
})

describe('Landing page while the session is unknown', () => {
  beforeEach(() => {
    authState = { status: 'loading' }
  })

  it('offers neither state rather than flashing the wrong one', () => {
    render(<LandingPage />)

    expect(screen.queryByRole('link', { name: /go to dashboard/i })).toBeNull()
    expect(screen.queryByRole('link', { name: /create an account/i })).toBeNull()
    expect(screen.queryByRole('link', { name: /log in/i })).toBeNull()
  })

  it('still renders the copy, which needs no session', () => {
    render(<LandingPage />)

    expect(
      screen.getByRole('heading', { level: 1, name: /what AI answers say about your brand/i }),
    ).toBeVisible()
    expect(screen.getByRole('heading', { name: /how it works/i })).toBeVisible()
  })
})
