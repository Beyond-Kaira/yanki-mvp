/** Semrush-like product shell navigation config. */

export type NavBadge = 'live' | 'na' | null

export type ShellSectionId =
  | 'home'
  | 'search-visibility'
  | 'ai-visibility'
  | 'free-checker'
  | 'methodology'
  | 'categories'
  | 'backlinks'
  | 'analytics'
  | 'reports'
  | 'settings'

export interface ShellFlyoutItem {
  id: string
  label: string
  href: string | null
  badge: NavBadge
}

export interface ShellSection {
  id: ShellSectionId
  label: string
  href: string | null
  /** When null, section is N/A (no flyout destinations). */
  flyoutTitle: string | null
  items: ShellFlyoutItem[]
}

export const SHELL_SECTIONS: ShellSection[] = [
  {
    id: 'home',
    label: 'Home',
    href: '/',
    flyoutTitle: null,
    items: [],
  },
  {
    id: 'search-visibility',
    label: 'Search Visibility',
    href: '/search-visibility',
    flyoutTitle: 'Search Visibility',
    items: [
      {
        id: 'overview',
        label: 'Overview',
        href: '/search-visibility',
        badge: 'live',
      },
      { id: 'site-audit', label: 'Site Audit', href: null, badge: 'na' },
      { id: 'positions', label: 'Position Tracking', href: null, badge: 'na' },
      { id: 'organic', label: 'Organic Research', href: null, badge: 'na' },
      { id: 'keywords', label: 'Keyword Magic', href: null, badge: 'na' },
      { id: 'onpage', label: 'On Page SEO Checker', href: null, badge: 'na' },
      { id: 'backlink-audit', label: 'Backlink Audit', href: null, badge: 'na' },
    ],
  },
  {
    id: 'ai-visibility',
    label: 'AI Visibility',
    href: '/ai-visibility',
    flyoutTitle: 'AI Visibility',
    items: [
      {
        id: 'overview',
        label: 'Overview',
        href: '/ai-visibility',
        badge: 'live',
      },
      {
        id: 'prompts',
        label: 'Prompts & Answers',
        href: '/ai-visibility/prompts',
        badge: 'live',
      },
      {
        id: 'citations',
        label: 'Citations',
        href: '/ai-visibility/citations',
        badge: 'live',
      },
      {
        id: 'drivers',
        label: 'Drivers & Gaps',
        href: '/ai-visibility/drivers',
        badge: 'live',
      },
      {
        id: 'sov',
        label: 'Share of voice timeline',
        href: null,
        badge: 'na',
      },
    ],
  },
  {
    id: 'free-checker',
    label: 'Free checker',
    href: '/checker',
    flyoutTitle: null,
    items: [],
  },
  {
    id: 'methodology',
    label: 'Methodology',
    href: '/methodology',
    flyoutTitle: null,
    items: [],
  },
  {
    id: 'categories',
    label: 'Categories',
    href: null,
    flyoutTitle: 'Categories',
    items: [{ id: 'cat-na', label: 'Category research', href: null, badge: 'na' }],
  },
  {
    id: 'backlinks',
    label: 'Backlinks',
    href: null,
    flyoutTitle: 'Backlinks',
    items: [{ id: 'bl-na', label: 'Backlink analytics', href: null, badge: 'na' }],
  },
  {
    id: 'analytics',
    label: 'Analytics',
    href: null,
    flyoutTitle: 'Analytics',
    items: [{ id: 'an-na', label: 'Traffic analytics', href: null, badge: 'na' }],
  },
  {
    id: 'reports',
    label: 'Reports',
    href: null,
    flyoutTitle: 'Reports',
    items: [{ id: 'rp-na', label: 'Scheduled reports', href: null, badge: 'na' }],
  },
  {
    id: 'settings',
    label: 'Settings',
    href: '/ai-visibility/settings',
    flyoutTitle: 'Settings',
    items: [
      { id: 'profile', label: 'Profile', href: '/ai-visibility/settings', badge: 'na' },
      { id: 'workspace', label: 'Workspace', href: null, badge: 'na' },
      { id: 'billing', label: 'Billing', href: null, badge: 'na' },
    ],
  },
]

export function sectionFromPath(pathname: string): ShellSectionId {
  if (pathname === '/' || pathname === '') return 'home'
  if (pathname.startsWith('/checker')) return 'free-checker'
  if (pathname.startsWith('/methodology')) return 'methodology'
  if (pathname.startsWith('/search-visibility')) return 'search-visibility'
  if (pathname.startsWith('/ai-visibility/settings')) return 'settings'
  if (pathname.startsWith('/ai-visibility')) return 'ai-visibility'
  if (pathname.startsWith('/analyses')) return 'ai-visibility'
  return 'home'
}

export function flyoutItemActive(pathname: string, item: ShellFlyoutItem): boolean {
  if (!item.href) return false
  if (item.href === '/ai-visibility') {
    return pathname === '/ai-visibility' || pathname === '/ai-visibility/'
  }
  if (item.href === '/search-visibility') {
    return (
      pathname === '/search-visibility' || pathname === '/search-visibility/'
    )
  }
  if (item.href === '/') {
    return pathname === '/' || pathname === ''
  }
  return pathname === item.href || pathname.startsWith(`${item.href}/`)
}

/** Paths that use the product shell (vertical nav) instead of marketing header. */
export function isShellPath(pathname: string): boolean {
  if (pathname === '/' || pathname === '') return true
  return (
    pathname.startsWith('/ai-visibility') ||
    pathname.startsWith('/search-visibility') ||
    pathname.startsWith('/checker') ||
    pathname.startsWith('/methodology') ||
    pathname.startsWith('/analyses')
  )
}
