import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { axeCheck } from './a11y'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => '/',
}))

vi.mock('@/lib/api', () => ({
  createAnalysis: vi.fn(),
}))

import UrlForm from '@/components/UrlForm'

describe('UrlForm accessibility', () => {
  it('has no axe violations on the default render', async () => {
    const { container } = render(
      <main>
        <UrlForm />
      </main>,
    )
    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('has no axe violations in the invalid-URL error state', async () => {
    const user = userEvent.setup()
    const { container } = render(
      <main>
        <UrlForm />
      </main>,
    )

    await user.type(screen.getByLabelText(/url/i), 'not a url')
    await user.click(screen.getByRole('button', { name: /run analysis/i }))

    // Exercises the aria-invalid + aria-describedby + role="alert" wiring.
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(await axeCheck(container)).toHaveNoViolations()
  })
})
