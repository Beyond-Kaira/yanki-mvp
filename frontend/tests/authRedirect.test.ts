import { describe, expect, it } from 'vitest'
import { loginHref, safeNext } from '@/lib/auth-redirect'

describe('safeNext', () => {
  it('falls back to the signed-in home when there is no destination', () => {
    expect(safeNext(null)).toBe('/dashboard')
    expect(safeNext(undefined)).toBe('/dashboard')
    expect(safeNext('')).toBe('/dashboard')
  })

  it('keeps a same-origin path, query and all', () => {
    expect(safeNext('/site-audit')).toBe('/site-audit')
    expect(safeNext('/ai-visibility?analysis=abc123')).toBe(
      '/ai-visibility?analysis=abc123',
    )
  })

  it('refuses an absolute URL', () => {
    expect(safeNext('https://evil.example')).toBe('/dashboard')
    expect(safeNext('http://evil.example/login')).toBe('/dashboard')
  })

  it('refuses a protocol-relative URL', () => {
    expect(safeNext('//evil.example')).toBe('/dashboard')
    expect(safeNext('//evil.example/steal')).toBe('/dashboard')
  })

  it('refuses a scheme that is not a path at all', () => {
    expect(safeNext('javascript:alert(1)')).toBe('/dashboard')
    expect(safeNext('data:text/html,<script>')).toBe('/dashboard')
  })
})

describe('loginHref', () => {
  it('encodes the destination into the query string', () => {
    expect(loginHref('/ai-visibility?analysis=abc123')).toBe(
      `/login?next=${encodeURIComponent('/ai-visibility?analysis=abc123')}`,
    )
  })

  it('never carries an unsafe destination through', () => {
    expect(loginHref('https://evil.example')).toBe(
      `/login?next=${encodeURIComponent('/dashboard')}`,
    )
  })
})
