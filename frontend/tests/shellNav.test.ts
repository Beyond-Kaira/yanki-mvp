import { describe, expect, it } from 'vitest'
import {
  ADMIN_PANEL_TABS,
  SHELL_SECTIONS,
  flyoutItemActive,
  isShellPath,
  sectionFromPath,
} from '@/lib/shell-nav'

/**
 * The navigation model, checked as data.
 *
 * Two rules this file exists to hold. The nav may not advertise a destination
 * that does not exist — a 'live' badge on a route nobody built is a promise the
 * product breaks on click. And the administration surface is called **Admin
 * Panel**, everywhere, in one voice: it was previously a leaf named "Members &
 * roles" buried under Settings, which is how a governance surface becomes
 * invisible to the person who needs it.
 */
describe('shell navigation', () => {
  it('gives the Admin Panel its own top-level section', () => {
    const admin = SHELL_SECTIONS.find((section) => section.id === 'admin')
    expect(admin).toBeDefined()
    expect(admin!.label).toBe('Admin Panel')
    expect(admin!.flyoutTitle).toBe('Admin Panel')
    expect(admin!.href).toBe('/admin')
  })

  it('lists members, invitations and the audit log under it, all real', () => {
    const admin = SHELL_SECTIONS.find((section) => section.id === 'admin')!
    expect(admin.items.map((item) => item.id)).toEqual([
      'members',
      'invitations',
      'audit',
    ])
    // Every one is a built destination, so every one is badged live.
    expect(admin.items.every((item) => item.href && item.badge === 'live')).toBe(true)
  })

  it('no longer hides administration inside Settings', () => {
    const settings = SHELL_SECTIONS.find((section) => section.id === 'settings')!
    expect(settings.items.some((item) => item.href === '/admin')).toBe(false)
  })

  it('routes every /admin path to the Admin Panel section, not to Settings', () => {
    expect(sectionFromPath('/admin')).toBe('admin')
    expect(sectionFromPath('/admin/invitations')).toBe('admin')
    expect(sectionFromPath('/admin/audit')).toBe('admin')
    expect(sectionFromPath('/settings')).toBe('settings')
  })

  it('keeps the Admin Panel inside the product shell', () => {
    expect(isShellPath('/admin')).toBe(true)
    expect(isShellPath('/admin/audit')).toBe(true)
  })

  it('does not put the public invitation-accept page in the shell', () => {
    // Whoever opens it usually has no account, so the signed-in chrome — and
    // the auth gate that comes with it — would be exactly wrong.
    expect(isShellPath('/invite/some-token')).toBe(false)
  })

  it('does not mark the members tab active on a sibling admin page', () => {
    const members = { id: 'members', label: 'Members & roles', href: '/admin', badge: 'live' as const }
    expect(flyoutItemActive('/admin', members)).toBe(true)
    // `startsWith('/admin')` would light up Members on the audit page too.
    expect(flyoutItemActive('/admin/audit', members)).toBe(false)
  })

  it('exposes the same three tabs to the panel chrome as to the nav', () => {
    const admin = SHELL_SECTIONS.find((section) => section.id === 'admin')!
    expect(ADMIN_PANEL_TABS.map((tab) => tab.href)).toEqual(
      admin.items.map((item) => item.href),
    )
  })

  it('promotes Backlinks from "soon" to a real destination', () => {
    // It was the file's one honest 'soon' while only the engine existed. The
    // screens now exist, so leaving it as 'soon' would understate the product
    // in the same way the old "N/A" badges overstated it.
    const backlinks = SHELL_SECTIONS.find((section) => section.id === 'backlinks')!
    expect(backlinks.href).toBe('/backlinks')
    expect(backlinks.items.every((item) => item.href && item.badge === 'live')).toBe(
      true,
    )
  })

  it('routes backlink paths to the Backlinks section and keeps them in the shell', () => {
    // Both helpers have to know about the prefix: one drives which nav entry
    // lights up, the other whether the signed-in chrome renders at all. Missing
    // the second is how a page ends up with no navigation on it.
    expect(sectionFromPath('/backlinks')).toBe('backlinks')
    expect(sectionFromPath('/backlinks/some-project-id')).toBe('backlinks')
    expect(isShellPath('/backlinks')).toBe(true)
    expect(isShellPath('/backlinks/some-project-id')).toBe(true)
  })

  it('never advertises a live destination without a route', () => {
    for (const section of SHELL_SECTIONS) {
      for (const item of section.items) {
        if (item.badge === 'live') expect(item.href).toBeTruthy()
        if (!item.href) expect(item.badge).toBe('soon')
      }
    }
  })
})
