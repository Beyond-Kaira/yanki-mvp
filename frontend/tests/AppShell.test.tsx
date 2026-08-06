import { render, screen } from '@testing-library/react'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import AppShell from '@/components/shell/AppShell'

beforeAll(() => {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: true,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    onchange: null,
    dispatchEvent: vi.fn(),
  }))
})

vi.mock('next/navigation', () => ({
  usePathname: () => '/dashboard',
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}))

vi.mock('@/components/AuthProvider', () => ({
  useAuth: () => ({
    status: 'authenticated',
    user: { email: 'someone@example.com', organization: null },
    signOut: vi.fn(),
  }),
}))

vi.mock('@/components/AnalysisSessionProvider', () => ({
  useAnalysisSession: () => ({ analysisId: null, setAnalysisId: vi.fn() }),
}))

describe('AppShell', () => {
  it('points the wordmark at the signed-in home, not the marketing page', () => {
    render(
      <AppShell>
        <p>page content</p>
      </AppShell>,
    )

    expect(screen.getByRole('link', { name: 'Yanki' })).toHaveAttribute('href', '/dashboard')
  })
})
