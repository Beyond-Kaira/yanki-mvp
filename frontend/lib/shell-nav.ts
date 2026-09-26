/** The product shell's navigation.
 *
 * Live entries must point to built routes. Requested feature inventories use
 * N/A for entries without a destination; that badge does not imply a delivery
 * date. "Soon" remains reserved for planned work.
 * Free checker and Methodology are reference links in the header and top bar.
 */

import { isPublicPath } from "@/lib/route-access";

export type NavBadge = 'live' | 'soon' | 'na' | null

export type ShellSectionId =
  | 'home'
  | 'search-visibility'
  | 'ai-visibility'
  | 'backlinks'
  | 'traffic-market'
  | 'content'
  | 'ai-pr'
  | 'advertising'
  | 'local'
  | 'social'
  | 'admin'
  | 'settings'

export interface ShellFlyoutItem {
  id: string;
  label: string;
  href: string | null;
  badge: NavBadge;
}

export interface ShellSection {
  id: ShellSectionId
  label: string
  href: string | null
  /** Null for sections without a flyout. */
  flyoutTitle: string | null
  items: ShellFlyoutItem[]
}

/** Visible features that do not have an application destination yet. */
function unavailable(id: string, label: string): ShellFlyoutItem {
  return { id, label, href: null, badge: 'na' }
}

export const SHELL_SECTIONS: ShellSection[] = [
  {
    id: "home",
    label: "Home",
    href: "/dashboard",
    flyoutTitle: null,
    items: [],
  },
  {
    id: "search-visibility",
    label: "Search Visibility",
    href: "/search-visibility",
    flyoutTitle: "Search Visibility",
    items: [
      {
        id: "overview",
        label: "Overview",
        href: "/search-visibility",
        badge: "live",
      },
      // Site Audit is fully built (crawler, worker, dashboard) and was badged
      // "N/A" — the single most misleading entry in the file.
      {
        id: "site-audit",
        label: "Site Audit",
        href: "/site-audit",
        badge: "live",
      },
      {
        id: "keyword-overview",
        label: "Keyword Overview",
        href: "/search-visibility/keywords",
        badge: "live",
      },
      {
        id: "keyword-magic",
        label: "Keyword Magic",
        href: "/search-visibility/keywords/magic",
        badge: "live",
      },
    ],
  },
  {
    id: "ai-visibility",
    label: "AI Visibility",
    href: "/ai-visibility",
    flyoutTitle: "AI Visibility",
    items: [
      {
        id: "overview",
        label: "Overview",
        href: "/ai-visibility",
        badge: "live",
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
        id: 'industry-citations',
        label: 'Top Cited Pages for Your Industry',
        href: '/ai-visibility/industry-citations',
        badge: 'live',
      },
      {
        id: "drivers",
        label: "Drivers & Gaps",
        href: "/ai-visibility/drivers",
        badge: "live",
      },
      // The record of what this organization has actually run. It belongs in
      // this section rather than under Home because a GEO analysis *is* the AI
      // Visibility product — and it exists at all because runs started
      // belonging to an organization in P7.6, which made "where are my previous
      // ones?" a question with a real answer for the first time.
      {
        id: "analysis-history",
        label: "Your analyses",
        href: "/analyses",
        badge: "live",
      },
      {
        id: "entities",
        label: "Entities",
        href: "/ai-visibility/entities",
        badge: "live",
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
       {
        id: "bl-inventory",
        label: "Backlink inventory",
        href: "/backlinks",
        badge: "live",
      },
    ],
  },
  {
    id: 'traffic-market',
    label: 'Traffic & Market',
    href: null,
    flyoutTitle: 'Traffic & Market',
    items: [
      unavailable('get-started', 'Get Started'),
      unavailable('traffic-analytics', 'Traffic Analytics'),
      unavailable('market-overview', 'Market Overview'),
      unavailable('competitor-monitoring', 'Competitor Monitoring'),
      unavailable('ai-traffic', 'AI Traffic'),
      unavailable('referral', 'Referral'),
      unavailable('organic-search', 'Organic Search'),
      unavailable('paid-search', 'Paid Search'),
      unavailable('organic-social', 'Organic Social'),
      unavailable('paid-social', 'Paid Social'),
      unavailable('email', 'Email'),
      unavailable('display-ads', 'Display Ads'),
      unavailable('sources-destinations', 'Sources & Destinations'),
      unavailable('top-pages', 'Top Pages'),
      unavailable('subfolders-subdomains', 'Subfolders & Subdomains'),
      unavailable('page-groups', 'Page Groups'),
      unavailable('usa', 'USA'),
      unavailable('countries', 'Countries'),
      unavailable('business-regions', 'Business Regions'),
      unavailable('geographical-regions', 'Geographical Regions'),
      unavailable('demographics', 'Demographics'),
      unavailable('audience-overlap', 'Audience Overlap'),
      unavailable('socioeconomics', 'Socioeconomics'),
      unavailable('behavior', 'Behavior'),
      unavailable('daily-trends', 'Daily Trends'),
      unavailable('industry-bulk-analysis', 'Industry & Bulk Analysis'),
      unavailable('trends-api', 'Trends API'),
      unavailable('trending-websites', 'Trending Websites'),
    ],
  },
  {
    id: 'content',
    label: 'Content',
    href: null,
    flyoutTitle: 'Content',
    items: [
      unavailable('content-dashboard', 'Content Dashboard'),
      unavailable('topic-finder', 'Topic Finder'),
      unavailable('seo-brief-generator', 'SEO Brief Generator'),
      unavailable('ai-article-generator', 'AI Article Generator'),
      unavailable('content-optimizer', 'Content Optimizer'),
      unavailable('converter-smm-email', 'Converter to SMM or Email'),
      unavailable('my-content', 'My Content'),
    ],
  },
  {
    id: 'ai-pr',
    label: 'AI PR',
    href: null,
    flyoutTitle: 'AI PR',
    items: [
      unavailable('dashboard', 'Dashboard'),
      unavailable('ai-cited-media', 'AI-Cited Media'),
      unavailable('contact-search', 'Contact Search'),
      unavailable('media-lists', 'Media Lists'),
      unavailable('your-emails', 'Your Emails'),
      unavailable('senders-domains', 'Senders and Domains'),
      unavailable('media-monitoring', 'Media Monitoring'),
      unavailable('alerts-digests', 'Alerts and Digests'),
    ],
  },
  {
    id: 'advertising',
    label: 'Advertising',
    href: null,
    flyoutTitle: 'Advertising',
    items: [
      unavailable('get-started', 'Get Started'),
      unavailable('ads-launch-assistant', 'Ads Launch Assistant'),
      unavailable('ads-ai-agent', 'Ads AI Agent'),
      unavailable('advertising-research', 'Advertising Research'),
      unavailable('pla-research', 'PLA Research'),
      unavailable('adclarity', 'AdClarity'),
    ],
  },
  {
    id: 'local',
    label: 'Local',
    href: null,
    flyoutTitle: 'Local',
    items: [
      unavailable('dashboard', 'Local Dashboard'),
      unavailable('listing-management', 'Listing Management'),
      unavailable('review-management', 'Review Management'),
      unavailable('gbp-optimization', 'GBP Optimization'),
      unavailable('gbp-ai-agent', 'GBP AI Agent'),
      unavailable('map-rank-tracker', 'Map Rank Tracker'),
    ],
  },
  {
    id: 'social',
    label: 'Social',
    href: null,
    flyoutTitle: 'Social',
    items: [
      unavailable('dashboard', 'Social Dashboard'),
      unavailable('social-poster', 'Social Poster'),
      unavailable('social-tracker', 'Social Tracker'),
      unavailable('social-content-insights', 'Social Content Insights'),
      unavailable('social-analytics', 'Social Analytics'),
      unavailable('influencer-analytics', 'Influencer Analytics'),
      unavailable('media-monitoring', 'Media Monitoring'),
    ],
  },
  
  {
    // The Admin Panel is a SECTION, not an item hidden inside Settings. Members,
    // invitations and the audit log are governance — a different job, done by a
    // different person, from "change my password" — and burying them one level
    // down under a personal-preferences heading is what made an account feel
    // like it granted nothing (tech-debt #52).
    id: "admin",
    label: "Admin Panel",
    href: "/admin",
    flyoutTitle: "Admin Panel",
    items: [
      {
        id: "members",
        label: "Members & roles",
        href: "/admin",
        badge: "live",
      },
      {
        id: "invitations",
        label: "Invitations",
        href: "/admin/invitations",
        badge: "live",
      },
      { id: "audit", label: "Audit log", href: "/admin/audit", badge: "live" },
    ],
  },
  {
    id: "settings",
    label: "Settings",
    href: "/settings",
    flyoutTitle: "Settings",
    items: [
      { id: "profile", label: "Profile", href: "/settings", badge: "live" },
      { id: "billing", label: "Plan & usage", href: null, badge: "soon" },
    ],
  },
];

/** The Admin Panel's own tabs, in the order the sub-pages present them. */
export const ADMIN_PANEL_TABS: { id: string; label: string; href: string }[] = [
  { id: "members", label: "Members & roles", href: "/admin" },
  { id: "invitations", label: "Invitations", href: "/admin/invitations" },
  { id: "audit", label: "Audit log", href: "/admin/audit" },
];

export function sectionFromPath(pathname: string): ShellSectionId {
  if (pathname === "/dashboard" || pathname === "/" || pathname === "")
    return "home";
  if (pathname.startsWith("/search-visibility")) return "search-visibility";
  if (pathname.startsWith("/site-audit")) return "search-visibility";
  if (pathname.startsWith("/admin")) return "admin";
  if (pathname.startsWith("/settings")) return "settings";
  if (pathname.startsWith("/ai-visibility")) return "ai-visibility";
  if (pathname.startsWith("/analyses")) return "ai-visibility";
  if (pathname.startsWith("/backlinks")) return "backlinks";
  return "home";
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
  "/",
  "/admin",
  "/ai-visibility",
  "/search-visibility",
  "/search-visibility/keywords",
]);

export function flyoutItemActive(
  pathname: string,
  item: ShellFlyoutItem,
): boolean {
  if (!item.href) return false;
  if (EXACT_MATCH_HREFS.has(item.href)) {
    const normalized =
      pathname.endsWith("/") && pathname !== "/"
        ? pathname.slice(0, -1)
        : pathname;
    return normalized === item.href || (item.href === "/" && normalized === "");
  }
  return pathname === item.href || pathname.startsWith(`${item.href}/`);
}

/** Paths that use the product shell (vertical nav) instead of marketing header.
 *
 * `/checker` and `/methodology` are deliberately absent. They are reachable
 * from both chromes now — a link in the header and in the shell's top bar — and
 * a page you reach by link does not need to carry the whole product rail. */
export function isShellPath(pathname: string): boolean {
  if (pathname === "/dashboard") return true;
  return (
    pathname.startsWith("/dashboard") ||
    pathname.startsWith("/admin") ||
    pathname.startsWith("/settings") ||
    pathname.startsWith("/site-audit") ||
    pathname.startsWith("/backlinks") ||
    pathname.startsWith("/ai-visibility") ||
    pathname.startsWith("/search-visibility") ||
    pathname.startsWith("/analyses")
  );
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
  if (!isShellPath(pathname)) return false;
  return signedIn || !isPublicPath(pathname);
}
