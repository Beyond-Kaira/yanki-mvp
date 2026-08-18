import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AppShell from '@/components/shell/AppShell'
import ShellStateProvider from '@/components/shell/ShellStateProvider'

const push = vi.fn()
let pathname = '/dashboard'

vi.mock('next/navigation', () => ({
  usePathname: () => pathname,
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(''),
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

function renderShell() {
  return render(
    <ShellStateProvider>
      <AppShell>
        <p>page body</p>
      </AppShell>
    </ShellStateProvider>,
  )
}

/** The rail only renders its wordmark once expanded, so it reads as the state. */
function expanded(): boolean {
  return screen.queryByText('Yanki') !== null
}

function rail(): HTMLElement {
  return document.getElementById('product-nav')!
}

function toolkits(): HTMLElement {
  return screen.getByRole('navigation', { name: /toolkits/i })
}

/** The row wrapping a section's button — what the pointer actually enters. */
function row(label: string): HTMLElement {
  return screen.getByRole('button', { name: label }).parentElement!
}

describe('AppShell rail', () => {
  beforeEach(() => {
    pathname = '/dashboard'
    push.mockClear()
    vi.useFakeTimers()
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
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('waits for hover intent before expanding', () => {
    renderShell()
    expect(expanded()).toBe(false)

    fireEvent.mouseEnter(toolkits())
    expect(expanded()).toBe(false)

    act(() => void vi.advanceTimersByTime(150))
    expect(expanded()).toBe(true)
  })

  // The point of the delay: reaching an icon and clicking it is a complete
  // gesture on its own, and the panel has no business opening over it.
  it('navigates from a collapsed icon without expanding', () => {
    renderShell()

    fireEvent.mouseEnter(toolkits())
    fireEvent.click(screen.getByRole('button', { name: 'AI Visibility' }))

    expect(push).toHaveBeenCalledWith('/ai-visibility')

    act(() => void vi.advanceTimersByTime(400))
    expect(expanded()).toBe(false)
  })

  it('keeps the rail open while the pointer crosses the wordmark', () => {
    renderShell()
    fireEvent.mouseEnter(toolkits())
    act(() => void vi.advanceTimersByTime(150))

    fireEvent.mouseEnter(screen.getByLabelText('Yanki').parentElement!)

    expect(expanded()).toBe(true)
  })

  it('does not expand from the wordmark alone', () => {
    renderShell()

    fireEvent.mouseEnter(screen.getByLabelText('Yanki').parentElement!)
    act(() => void vi.advanceTimersByTime(400))

    expect(expanded()).toBe(false)
  })

  it('forgives a pointer that clips the rail edge and returns', () => {
    renderShell()
    fireEvent.mouseEnter(toolkits())
    act(() => void vi.advanceTimersByTime(150))

    fireEvent.mouseLeave(rail())
    act(() => void vi.advanceTimersByTime(60))
    expect(expanded()).toBe(true)

    fireEvent.mouseEnter(rail())
    act(() => void vi.advanceTimersByTime(400))
    expect(expanded()).toBe(true)
  })

  it('closes once the pointer has been gone long enough', () => {
    renderShell()
    fireEvent.mouseEnter(toolkits())
    act(() => void vi.advanceTimersByTime(150))

    fireEvent.mouseLeave(rail())
    act(() => void vi.advanceTimersByTime(200))

    expect(expanded()).toBe(false)
  })

  // The whole fix: a submenu may not participate in the icon column's flow, or
  // opening one shoves every icon below it out from under the pointer.
  it('renders the desktop submenu outside the icon column flow', () => {
    renderShell()
    fireEvent.mouseEnter(toolkits())
    act(() => void vi.advanceTimersByTime(150))

    fireEvent.mouseEnter(
      screen.getByRole('button', { name: 'AI Visibility' }).parentElement!,
    )

    const submenu = document.getElementById(
      'shell-subnav-desktop-ai-visibility',
    )
    expect(submenu).not.toBeNull()
    expect(submenu!.className).toContain('absolute')
    expect(
      within(submenu!).getByRole('link', { name: /Prompts & Answers/ }),
    ).toBeVisible()
  })

  it('stays open across a routed shell remount until the pointer leaves', () => {
    const { rerender } = render(
      <ShellStateProvider>
        <AppShell key="/dashboard">
          <p>page body</p>
        </AppShell>
      </ShellStateProvider>,
    )

    fireEvent.mouseEnter(toolkits())
    act(() => void vi.advanceTimersByTime(150))
    fireEvent.mouseEnter(row('AI Visibility'))
    expect(expanded()).toBe(true)
    expect(
      document.getElementById('shell-subnav-desktop-ai-visibility'),
    ).not.toBeNull()

    pathname = '/ai-visibility/prompts'
    rerender(
      <ShellStateProvider>
        <AppShell key="/ai-visibility/prompts">
          <p>page body</p>
        </AppShell>
      </ShellStateProvider>,
    )

    expect(expanded()).toBe(true)
    expect(
      document.getElementById('shell-subnav-desktop-ai-visibility'),
    ).not.toBeNull()

    fireEvent.mouseLeave(rail())
    act(() => void vi.advanceTimersByTime(200))
    expect(expanded()).toBe(false)
  })

  it('keeps the same shell mounted while routed content changes', () => {
    const { rerender } = render(
      <ShellStateProvider>
        <AppShell>
          <p>dashboard body</p>
        </AppShell>
      </ShellStateProvider>,
    )
    const mountedRail = rail()

    pathname = '/ai-visibility'
    rerender(
      <ShellStateProvider>
        <AppShell>
          <p>AI visibility body</p>
        </AppShell>
      </ShellStateProvider>,
    )

    expect(rail()).toBe(mountedRail)
    expect(screen.getByText('AI visibility body')).toBeInTheDocument()
  })

  it('shows a submenu only for the section under the pointer', () => {
    pathname = '/ai-visibility'
    renderShell()
    fireEvent.mouseEnter(toolkits())
    act(() => void vi.advanceTimersByTime(150))

    expect(
      document.getElementById('shell-subnav-desktop-ai-visibility'),
    ).toBeNull()

    fireEvent.mouseEnter(row('Admin Panel'))

    expect(document.getElementById('shell-subnav-desktop-admin')).not.toBeNull()
    expect(
      document.getElementById('shell-subnav-desktop-ai-visibility'),
    ).toBeNull()
  })

  // Reaching the bottom item of an open panel means cutting diagonally across
  // the rows below your own. Handing them the panel on contact would take it
  // out from under the pointer halfway there.
  it('holds an open panel while the pointer cuts across other rows', () => {
    renderShell()
    fireEvent.mouseEnter(toolkits())
    act(() => void vi.advanceTimersByTime(150))
    fireEvent.mouseEnter(row('AI Visibility'))

    const aiPanel = () =>
      document.getElementById('shell-subnav-desktop-ai-visibility')
    expect(aiPanel()).not.toBeNull()

    fireEvent.mouseEnter(row('Backlinks'))
    fireEvent.mouseEnter(row('Settings'))
    expect(aiPanel()).not.toBeNull()

    fireEvent.mouseEnter(row('Admin Panel'))
    act(() => void vi.advanceTimersByTime(120))

    expect(document.getElementById('shell-subnav-desktop-admin')).not.toBeNull()
    expect(aiPanel()).toBeNull()
  })

  // Reaching an item low in the panel means crossing the rows underneath at
  // whatever speed a hand moves — far longer than the plain dwell allows.
  it('gives a pointer travelling toward the panel a longer reprieve', () => {
    renderShell()
    fireEvent.mouseEnter(toolkits())
    act(() => void vi.advanceTimersByTime(150))
    fireEvent.mouseEnter(row('AI Visibility'), { clientX: 40 })

    const aiPanel = () =>
      document.getElementById('shell-subnav-desktop-ai-visibility')
    expect(aiPanel()).not.toBeNull()

    fireEvent.mouseMove(rail(), { clientX: 90 })
    fireEvent.mouseEnter(row('Backlinks'), { clientX: 140 })

    act(() => void vi.advanceTimersByTime(300))
    expect(aiPanel()).not.toBeNull()

    // Sitting on the row that long is a decision, not a trajectory.
    act(() => void vi.advanceTimersByTime(300))
    expect(aiPanel()).toBeNull()
  })

  // The rows crossed on the way in each queued a swap. Reaching the panel has
  // to settle them, or one comes due while you are reading it.
  it('keeps the panel once the pointer is inside it', () => {
    renderShell()
    fireEvent.mouseEnter(toolkits())
    act(() => void vi.advanceTimersByTime(150))
    fireEvent.mouseEnter(row('AI Visibility'))

    const panel = document.getElementById('shell-subnav-desktop-ai-visibility')!
    expect(panel).not.toBeNull()

    fireEvent.mouseEnter(row('Backlinks'))
    fireEvent.mouseEnter(panel)
    act(() => void vi.advanceTimersByTime(1000))

    expect(
      document.getElementById('shell-subnav-desktop-ai-visibility'),
    ).not.toBeNull()
    expect(
      within(
        document.getElementById('shell-subnav-desktop-ai-visibility')!,
      ).getByRole('link', { name: /Citations/ }),
    ).toBeVisible()
  })
})
