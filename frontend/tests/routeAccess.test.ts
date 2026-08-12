import { describe, expect, it } from 'vitest'
import { isPublicPath } from '@/lib/route-access'

describe('isPublicPath', () => {
  it('lets a signed-out visitor reach the marketing and auth screens', () => {
    expect(isPublicPath('/')).toBe(true)
    expect(isPublicPath('/login')).toBe(true)
    expect(isPublicPath('/signup')).toBe(true)
    expect(isPublicPath('/checker')).toBe(true)
    expect(isPublicPath('/methodology')).toBe(true)
  })

  it('keeps capability URLs reachable', () => {
    expect(isPublicPath('/analyses/1f0c9d2e-0000-4000-8000-000000000000')).toBe(true)
    expect(isPublicPath('/checker/1f0c9d2e-0000-4000-8000-000000000000')).toBe(true)
    expect(isPublicPath('/invite/some-token')).toBe(true)
  })

  it('gates the lists those capability URLs belong to', () => {
    expect(isPublicPath('/analyses')).toBe(false)
    expect(isPublicPath('/dashboard')).toBe(false)
    expect(isPublicPath('/settings')).toBe(false)
  })

  it('gates every product surface', () => {
    for (const path of [
      '/admin',
      '/admin/audit',
      '/admin/invitations',
      '/ai-visibility',
      '/ai-visibility/citations',
      '/ai-visibility/drivers',
      '/ai-visibility/prompts',
      '/ai-visibility/settings',
      '/search-visibility',
      '/backlinks',
      '/backlinks/abc',
      '/site-audit',
      '/site-audit/abc',
    ]) {
      expect(isPublicPath(path), path).toBe(false)
    }
  })

  it('gates an unknown route rather than exposing it', () => {
    expect(isPublicPath('/billing')).toBe(false)
    expect(isPublicPath('/some/deep/new/page')).toBe(false)
  })

  it('does not let a deeper path ride in on a public prefix', () => {
    expect(isPublicPath('/analyses/abc/edit')).toBe(false)
    expect(isPublicPath('/checker/abc/raw')).toBe(false)
  })

  it('treats a trailing slash as the same route', () => {
    expect(isPublicPath('/checker/')).toBe(true)
    expect(isPublicPath('/dashboard/')).toBe(false)
  })
})
