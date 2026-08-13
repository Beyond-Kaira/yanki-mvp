import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ShellAuthBar from '@/components/shell/ShellAuthBar'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

const authState = {
  status: 'authenticated' as string,
  user: { email: 'owner@acme.test' } as unknown,
}

vi.mock('@/components/AuthProvider', () => ({
  useAuth: () => ({ ...authState, signOut: vi.fn() }),
}))

/**
 * The methodology and the free checker left the product rail. Without them in
 * this bar a signed-in reader would have no route back to either from inside
 * the product — the rail was their only entry point, and the marketing header
 * that now carries them does not render here.
 */
describe('ShellAuthBar', () => {
  it('carries the reference links, opening each in a new tab', () => {
    render(<ShellAuthBar />)

    const methodology = screen.getByRole('link', { name: 'Methodology' })
    const checker = screen.getByRole('link', { name: 'Free checker' })
    expect(methodology).toHaveAttribute('href', '/methodology')
    expect(checker).toHaveAttribute('href', '/checker')
    for (const link of [methodology, checker]) {
      // A run in progress is state worth keeping; a same-tab hop discards the
      // screen it was on to show a page you glance at and leave.
      expect(link).toHaveAttribute('target', '_blank')
      expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'))
    }
  })

  it('still shows the account it was already responsible for', () => {
    render(<ShellAuthBar />)

    expect(screen.getByText('owner@acme.test')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /log out/i })).toBeInTheDocument()
  })
})
