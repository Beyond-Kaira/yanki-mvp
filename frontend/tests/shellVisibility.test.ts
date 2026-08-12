import { describe, expect, it } from 'vitest'
import { showsAppShell } from '@/lib/shell-nav'

/**
 * The shell is the signed-in product surface. On a public route it is an
 * upgrade the visitor has earned, not the default chrome — so the question is
 * never "is this a shell route" alone.
 */
describe('showsAppShell', () => {
  it('keeps the shell off routes that never had one', () => {
    expect(showsAppShell('/', true)).toBe(false)
    expect(showsAppShell('/login', true)).toBe(false)
    expect(showsAppShell('/signup', false)).toBe(false)
  })

  it('drops the shell for a signed-out visitor on a public route', () => {
    expect(showsAppShell('/methodology', false)).toBe(false)
    expect(showsAppShell('/checker', false)).toBe(false)
    expect(showsAppShell('/checker/abc123', false)).toBe(false)
    // A shared result is a capability URL, so its reader may well be anonymous.
    expect(showsAppShell('/analyses/abc123', false)).toBe(false)
  })

  it('gives the same public route its shell once signed in', () => {
    expect(showsAppShell('/methodology', true)).toBe(true)
    expect(showsAppShell('/checker', true)).toBe(true)
    expect(showsAppShell('/analyses/abc123', true)).toBe(true)
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
