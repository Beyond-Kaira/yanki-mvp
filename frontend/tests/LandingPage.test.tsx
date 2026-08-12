import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import LandingPage from '@/app/page'

/**
 * The operator's complaint was that a fresh session "navigates directly to the
 * search page". These assert the opposite property directly: `/` explains the
 * product and offers a way in, and does NOT render the signed-in application.
 *
 * The way in is now a single link to `/dashboard`. Signed out, the guard turns
 * that into `/login?next=/dashboard`, so the front door still leads somewhere
 * for a visitor without a session.
 */
describe('Landing page', () => {
  it('explains what the product does', () => {
    render(<LandingPage />)

    expect(
      screen.getByRole('heading', { level: 1, name: /what AI answers say about your brand/i }),
    ).toBeVisible()
  })

  it('offers one way in, and it points at the dashboard', () => {
    render(<LandingPage />)

    expect(screen.getByRole('link', { name: /go to dashboard/i })).toHaveAttribute(
      'href',
      '/dashboard',
    )
  })

  it('carries no other call to action', () => {
    render(<LandingPage />)

    expect(screen.getAllByRole('link')).toHaveLength(1)
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
