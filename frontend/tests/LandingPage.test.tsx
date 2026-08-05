import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import LandingPage from '@/app/page'

/**
 * The operator's complaint was that a fresh session "navigates directly to the
 * search page". These assert the opposite property directly: `/` explains the
 * product and offers a way in, and does NOT render the signed-in application.
 */
describe('Landing page', () => {
  it('explains what the product does', () => {
    render(<LandingPage />)

    expect(
      screen.getByRole('heading', { level: 1, name: /what AI answers say about your brand/i }),
    ).toBeVisible()
  })

  it('offers both a way in and a way to try it', () => {
    render(<LandingPage />)

    expect(screen.getAllByRole('link', { name: /create an account/i }).length).toBeGreaterThan(0)
    expect(screen.getByRole('link', { name: /log in/i })).toHaveAttribute('href', '/login')
    expect(screen.getByRole('link', { name: /free checker/i })).toHaveAttribute(
      'href',
      '/checker',
    )
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
