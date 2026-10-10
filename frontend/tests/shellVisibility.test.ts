import { describe, expect, it } from 'vitest'
import { showsAppShell } from '@/lib/shell-nav'

/** The shell belongs to product routes, not retired URLs or public pages. */
describe('showsAppShell', () => {
  it('keeps the shell off routes that never had one', () => {
    expect(showsAppShell('/', true)).toBe(false)
    expect(showsAppShell('/login', true)).toBe(false)
    expect(showsAppShell('/signup', false)).toBe(false)
  })

  it('does not show a shell for retired analysis URLs', () => {
    expect(showsAppShell('/analyses/abc123', false)).toBe(false)
    expect(showsAppShell('/analyses/abc123', true)).toBe(false)
  })

  /**
   * The free checker and the methodology are reference pages reached by a link
   * in the chrome, not sections of the product. They wear the marketing header
   * for everyone — being signed in no longer changes the answer.
   */
  it('never gives the reference pages a shell', () => {
    expect(showsAppShell('/methodology', false)).toBe(false)
    expect(showsAppShell('/methodology', true)).toBe(false)
    expect(showsAppShell('/checker', false)).toBe(false)
    expect(showsAppShell('/checker', true)).toBe(false)
    expect(showsAppShell('/checker/abc123', true)).toBe(false)
  })

  /**
   * A gated route keeps its shell either way. Signed out, the visitor is on
   * their way to /login and RequireAuth renders inside the shell; swapping in
   * the marketing header for that one frame would be a second flash on top of
   * the redirect.
   */
  it('keeps the shell on gated routes regardless of session', () => {
    expect(showsAppShell('/dashboard', false)).toBe(true)
    expect(showsAppShell('/analyses', false)).toBe(true)
    expect(showsAppShell('/settings', false)).toBe(true)
    expect(showsAppShell('/site-audit', false)).toBe(true)
  })

  it('reads a trailing slash as the same route', () => {
    expect(showsAppShell('/methodology/', false)).toBe(false)
  })
})
