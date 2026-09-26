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

  it('keeps Site Audit under Search Visibility', () => {
    expect(sectionFromPath('/site-audit')).toBe('search-visibility')
    expect(sectionFromPath('/site-audit/project-id')).toBe('search-visibility')
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

  it('shows the complete Traffic & Market inventory as unavailable', () => {
    const traffic = SHELL_SECTIONS.find((section) => section.id === 'traffic-market')!
    expect(traffic.href).toBeNull()
    expect(traffic.items.map((item) => item.label)).toEqual([
      'Get Started',
      'Traffic Analytics',
      'Market Overview',
      'Competitor Monitoring',
      'AI Traffic',
      'Referral',
      'Organic Search',
      'Paid Search',
      'Organic Social',
      'Paid Social',
      'Email',
      'Display Ads',
      'Sources & Destinations',
      'Top Pages',
      'Subfolders & Subdomains',
      'Page Groups',
      'USA',
      'Countries',
      'Business Regions',
      'Geographical Regions',
      'Demographics',
      'Audience Overlap',
      'Socioeconomics',
      'Behavior',
      'Daily Trends',
      'Industry & Bulk Analysis',
      'Trends API',
      'Trending Websites',
    ])
    expect(traffic.items.every((item) => item.href === null && item.badge === 'na')).toBe(true)
  })

  it('shows all seven Content tools as unavailable', () => {
    const content = SHELL_SECTIONS.find((section) => section.id === 'content')!
    expect(content.href).toBeNull()
    expect(content.items.map((item) => item.label)).toEqual([
      'Content Dashboard',
      'Topic Finder',
      'SEO Brief Generator',
      'AI Article Generator',
      'Content Optimizer',
      'Converter to SMM or Email',
      'My Content',
    ])
    expect(content.items.every((item) => item.href === null && item.badge === 'na')).toBe(true)
  })

  it('shows all eight AI PR tools as unavailable', () => {
    const aiPr = SHELL_SECTIONS.find((section) => section.id === 'ai-pr')!
    expect(aiPr.href).toBeNull()
    expect(aiPr.items.map((item) => item.label)).toEqual([
      'Dashboard',
      'AI-Cited Media',
      'Contact Search',
      'Media Lists',
      'Your Emails',
      'Senders and Domains',
      'Media Monitoring',
      'Alerts and Digests',
    ])
    expect(aiPr.items.every((item) => item.href === null && item.badge === 'na')).toBe(true)
  })

  it('shows all six Advertising tools as unavailable', () => {
    const advertising = SHELL_SECTIONS.find((section) => section.id === 'advertising')!
    expect(advertising.href).toBeNull()
    expect(advertising.items.map((item) => item.label)).toEqual([
      'Get Started',
      'Ads Launch Assistant',
      'Ads AI Agent',
      'Advertising Research',
      'PLA Research',
      'AdClarity',
    ])
    expect(advertising.items.every((item) => item.href === null && item.badge === 'na')).toBe(true)
  })

  it('shows all six Local tools as unavailable', () => {
    const local = SHELL_SECTIONS.find((section) => section.id === 'local')!
    expect(local.href).toBeNull()
    expect(local.items.map((item) => item.label)).toEqual([
      'Local Dashboard',
      'Listing Management',
      'Review Management',
      'GBP Optimization',
      'GBP AI Agent',
      'Map Rank Tracker',
    ])
    expect(local.items.every((item) => item.href === null && item.badge === 'na')).toBe(true)
  })

  it('shows all seven Social tools as unavailable', () => {
    const social = SHELL_SECTIONS.find((section) => section.id === 'social')!
    expect(social.href).toBeNull()
    expect(social.items.map((item) => item.label)).toEqual([
      'Social Dashboard',
      'Social Poster',
      'Social Tracker',
      'Social Content Insights',
      'Social Analytics',
      'Influencer Analytics',
      'Media Monitoring',
    ])
    expect(social.items.every((item) => item.href === null && item.badge === 'na')).toBe(true)
  })

  /**
   * The rail lists what the account can do. A document and a signed-out demo
   * are neither, and they took two of its eight rows; they are reference links
   * in the chrome now. The pages themselves still exist and stay public.
   */
  it('keeps the reference pages out of the rail entirely', () => {
    const hrefs = SHELL_SECTIONS.flatMap((section) => [
      section.href,
      ...section.items.map((item) => item.href),
    ])
    expect(hrefs).not.toContain('/checker')
    expect(hrefs).not.toContain('/methodology')
    expect(isShellPath('/checker')).toBe(false)
    expect(isShellPath('/checker/abc123')).toBe(false)
    expect(isShellPath('/methodology')).toBe(false)
    // With no section of their own they fall back to Home rather than lighting
    // up a row that has nothing to do with the page.
    expect(sectionFromPath('/methodology')).toBe('home')
  })

  it('never advertises a live destination without a route', () => {
    for (const section of SHELL_SECTIONS) {
      for (const item of section.items) {
        if (item.badge === 'live') expect(item.href).toBeTruthy()
        if (!item.href) expect(['soon', 'na']).toContain(item.badge)
      }
    }
  })
})
