/** The product shell's navigation.
 *
 * One rule governs this file: **the nav may not advertise something that does
 * not exist.** It shipped with fifteen entries badged "N/A" — Position
 * Tracking, Keyword Magic, Backlink Audit, Traffic Analytics and the rest —
 * which read to a customer as a roadmap commitment nobody had made, and made a
 * feature that DID exist (Site Audit) look equally unavailable.
 *
 * So each entry is now one of three things:
 *   - a real destination, badged 'live';
 *   - deliberately absent, if the feature does not exist;
 *   - present and honestly marked 'soon', reserved for work that is genuinely
 *     underway and has a card on the plan.
 *
 * "N/A" is gone entirely: it told the user nothing except that something was
 * missing, without saying whether it was coming.
 *
 * A second rule followed from the first: **the rail lists what the account can
 * do.** Free checker and Methodology are not that. One is a demo aimed at a
 * visitor who has no account, the other is a document explaining how the score
 * is computed — neither is a place you work. They took two of eight rows here
 * and now live in the marketing header and the shell's top bar instead, where a
 * reference link belongs.
 */

import { isPublicPath } from '@/lib/route-access'

export type NavBadge = 'live' | 'soon' | null

export type ShellSectionId =
  | 'home'
  | 'search-visibility'
  | 'ai-visibility'
  | 'backlinks'
  | 'admin'
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
    href: '/dashboard',
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
      // Site Audit is fully built (crawler, worker, dashboard) and was badged
      // "N/A" — the single most misleading entry in the file.
      { id: 'site-audit', label: 'Site Audit', href: '/site-audit', badge: 'live' },
      {
        id: 'keyword-overview',
        label: 'Keyword Overview',
        href: '/search-visibility/keywords',
        badge: 'live',
      },
      {
        id: 'keyword-magic',
        label: 'Keyword Magic',
        href: '/search-visibility/keywords/magic',
        badge: 'live',
      },
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
      // The record of what this organization has actually run. It belongs in
      // this section rather than under Home because a GEO analysis *is* the AI
      // Visibility product — and it exists at all because runs started
      // belonging to an organization in P7.6, which made "where are my previous
      // ones?" a question with a real answer for the first time.
      {
        id: 'analysis-history',
        label: 'Your analyses',
        href: '/analyses',
        badge: 'live',
      },
    ],
  },
  {
    // Now a real destination. The engine shipped in session 21, the API in 23,
    // and these screens complete P8.3 — so the entry graduates from 'soon' to
    // 'live' under this file's own rule.
    //
    // 'live' is the honest badge even though BACKLINKS_ENABLED is off in
    // production today: the screens exist and are reachable, and a customer who
    // opens one is told plainly that no index is connected yet. That is a
    // different statement from "this feature does not exist", which is what
    // 'soon' claimed and what a hidden entry would imply.
    id: 'backlinks',
    label: 'Backlinks',
    href: '/backlinks',
    flyoutTitle: 'Backlinks',
    items: [
      { id: 'bl-inventory', label: 'Backlink inventory', href: '/backlinks', badge: 'live' },
    ],
  },
  {
    // The Admin Panel is a SECTION, not an item hidden inside Settings. Members,
    // invitations and the audit log are governance — a different job, done by a
    // different person, from "change my password" — and burying them one level
    // down under a personal-preferences heading is what made an account feel
    // like it granted nothing (tech-debt #52).
    id: 'admin',
    label: 'Admin Panel',
    href: '/admin',
    flyoutTitle: 'Admin Panel',
    items: [
      { id: 'members', label: 'Members & roles', href: '/admin', badge: 'live' },
      { id: 'invitations', label: 'Invitations', href: '/admin/invitations', badge: 'live' },
      { id: 'audit', label: 'Audit log', href: '/admin/audit', badge: 'live' },
    ],
  },
  {
    id: 'settings',
    label: 'Settings',
    href: '/settings',
    flyoutTitle: 'Settings',
    items: [
      { id: 'profile', label: 'Profile', href: '/settings', badge: 'live' },
      { id: 'billing', label: 'Plan & usage', href: null, badge: 'soon' },
    ],
  },
]

/** The Admin Panel's own tabs, in the order the sub-pages present them. */
export const ADMIN_PANEL_TABS: { id: string; label: string; href: string }[] = [
  { id: 'members', label: 'Members & roles', href: '/admin' },
  { id: 'invitations', label: 'Invitations', href: '/admin/invitations' },
  { id: 'audit', label: 'Audit log', href: '/admin/audit' },
]

export function sectionFromPath(pathname: string): ShellSectionId {
  if (pathname === '/dashboard' || pathname === '/' || pathname === '') return 'home'
  if (pathname.startsWith('/search-visibility')) return 'search-visibility'
  if (pathname.startsWith('/site-audit')) return 'search-visibility'
  if (pathname.startsWith('/admin')) return 'admin'
  if (pathname.startsWith('/settings')) return 'settings'
  if (pathname.startsWith('/ai-visibility')) return 'ai-visibility'
  if (pathname.startsWith('/analyses')) return 'ai-visibility'
  if (pathname.startsWith('/backlinks')) return 'backlinks'
  return 'home'
}

/**
 * Hrefs that are both a destination AND the prefix of their siblings.
 *
 * `/admin` is the Members page and also the parent of `/admin/audit`; the
 * default subtree match would light up "Members & roles" while you are reading
 * the audit log. These match exactly instead — the same reason the two
 * visibility overviews are here.
 */
const EXACT_MATCH_HREFS = new Set([
  '/',
  '/admin',
  '/ai-visibility',
  '/search-visibility',
  '/search-visibility/keywords',
])

export function flyoutItemActive(pathname: string, item: ShellFlyoutItem): boolean {
  if (!item.href) return false
  if (EXACT_MATCH_HREFS.has(item.href)) {
    const normalized = pathname.endsWith('/') && pathname !== '/' ? pathname.slice(0, -1) : pathname
    return normalized === item.href || (item.href === '/' && normalized === '')
  }
  return pathname === item.href || pathname.startsWith(`${item.href}/`)
}

/** Paths that use the product shell (vertical nav) instead of marketing header.
 *
 * `/checker` and `/methodology` are deliberately absent. They are reachable
 * from both chromes now — a link in the header and in the shell's top bar — and
 * a page you reach by link does not need to carry the whole product rail. */
export function isShellPath(pathname: string): boolean {
  if (pathname === '/dashboard') return true
  return (
    pathname.startsWith('/dashboard') ||
    pathname.startsWith('/admin') ||
    pathname.startsWith('/settings') ||
    pathname.startsWith('/site-audit') ||
    pathname.startsWith('/backlinks') ||
    pathname.startsWith('/ai-visibility') ||
    pathname.startsWith('/search-visibility') ||
    pathname.startsWith('/analyses')
  )
}

/**
 * Whether this visitor gets the product shell on this route.
 *
 * One route is public *and* wears the shell: `/analyses/:id`, the capability URL
 * that makes a result shareable. For a signed-out reader the rail there
 * advertised a product they had no account for, ending in a "Not signed in"
 * card where the account should be. So on a public route the shell is an
 * upgrade the session earns, and the marketing header is the default.
 *
 * `signedIn` is false while the session is still resolving, which is
 * deliberate: on a public route the anonymous chrome is the safe guess, and a
 * rail that appears for one frame and then vanishes is the same wrong answer
 * with a flicker attached. Gated routes are unaffected either way — they keep
 * the shell while `RequireAuth` renders inside it.
 */
export function showsAppShell(pathname: string, signedIn: boolean): boolean {
  if (!isShellPath(pathname)) return false
  return signedIn || !isPublicPath(pathname)
}
