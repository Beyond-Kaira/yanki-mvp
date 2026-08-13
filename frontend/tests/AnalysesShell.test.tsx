import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ShellStateProvider from '@/components/shell/ShellStateProvider'
import AppShell from '@/components/shell/AppShell'
import ShellLayout from '@/app/analyses/layout'
import AnalysisHistoryPage from '@/app/analyses/page'

vi.mock('next/navigation', () => ({
  usePathname: () => '/analyses',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

vi.mock('next/image', () => ({
  default: ({ src, alt }: { src: string; alt: string }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt={alt} />
  ),
}))

vi.mock('@/components/shell/ShellAuthBar', () => ({
  default: () => <div data-testid="auth-bar" />,
}))

vi.mock('@/components/AuthProvider', () => ({
  useAuth: () => ({
    status: 'authenticated',
    user: {
      email: 'owner@acme.test',
      role: 'owner',
      organization: { name: 'Acme' },
    },
  }),
}))

vi.mock('@/components/AnalysisSessionProvider', () => ({
  useAnalysisSession: () => ({ analysisId: null }),
}))

vi.mock('@/app/analyses/AnalysisHistoryClient', () => ({
  default: () => <p>history</p>,
}))

/**
 * Next renders the route's layout around its page, so anything both of them
 * mount appears twice. The shell is the visible casualty: two nav rails and
 * two top bars stacked down the screen.
 */
describe('/analyses shell', () => {
  beforeEach(() => {
    // jsdom ships no matchMedia; the rail reads it to decide desktop vs drawer.
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockReturnValue({
        matches: true,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders exactly one product navigation rail', () => {
    render(
      <ShellStateProvider>
        <AppShell>
          <ShellLayout>
            <AnalysisHistoryPage />
          </ShellLayout>
        </AppShell>
      </ShellStateProvider>,
    )

    expect(screen.getAllByLabelText('Product navigation')).toHaveLength(1)
  })

  it('renders exactly one top bar', () => {
    render(
      <ShellStateProvider>
        <AppShell>
          <ShellLayout>
            <AnalysisHistoryPage />
          </ShellLayout>
        </AppShell>
      </ShellStateProvider>,
    )

    expect(screen.getAllByTestId('auth-bar')).toHaveLength(1)
  })
})
