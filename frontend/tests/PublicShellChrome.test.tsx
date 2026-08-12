import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ShellStateProvider from '@/components/shell/ShellStateProvider'
import AppShell from '@/components/shell/AppShell'
import SiteHeader from '@/components/SiteHeader'

const authState = { status: 'anonymous' as string, user: null as unknown }

vi.mock('next/navigation', () => ({
  usePathname: () => '/methodology',
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
  useAuth: () => ({ ...authState, signOut: vi.fn() }),
}))

vi.mock('@/components/AnalysisSessionProvider', () => ({
  useAnalysisSession: () => ({ analysisId: null }),
}))

const SIGNED_IN = {
  status: 'authenticated',
  user: {
    email: 'owner@acme.test',
    role: 'owner',
    organization: { name: 'Acme' },
  },
}

function renderRoute() {
  return render(
    <ShellStateProvider>
      <SiteHeader />
      <AppShell>
        <p>methodology</p>
      </AppShell>
    </ShellStateProvider>,
  )
}

/**
 * `/methodology` is public and a shell route at once, so it is the one place
 * the two chromes could both claim the page — or, as shipped, the wrong one
 * could: a signed-out reader was given the full product rail, down to a
 * "Not signed in" card where the account should be.
 */
describe('public shell route chrome', () => {
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
    authState.status = 'anonymous'
    authState.user = null
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows a signed-out reader the marketing header, not the product rail', () => {
    renderRoute()

    expect(screen.queryByLabelText('Product navigation')).not.toBeInTheDocument()
    expect(screen.queryByTestId('auth-bar')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Sign up' })).toBeInTheDocument()
    expect(screen.getByText('methodology')).toBeInTheDocument()
  })

  it('withholds the rail while the session is still unknown', () => {
    // A rail that appears and then vanishes is the same wrong answer, shown
    // briefly. On a public route the marketing header is the safe default.
    authState.status = 'loading'
    renderRoute()

    expect(screen.queryByLabelText('Product navigation')).not.toBeInTheDocument()
  })

  it('gives a signed-in reader the product rail and no marketing header', () => {
    authState.status = SIGNED_IN.status
    authState.user = SIGNED_IN.user
    renderRoute()

    expect(screen.getByLabelText('Product navigation')).toBeInTheDocument()
    expect(screen.getByTestId('auth-bar')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Sign up' })).not.toBeInTheDocument()
    expect(screen.getByText('methodology')).toBeInTheDocument()
  })
})
