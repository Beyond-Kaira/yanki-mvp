import Link from 'next/link'

/**
 * Methodology and the free checker, as reference links.
 *
 * Both used to be sections of the product rail, which put a document and a
 * signed-out demo alongside the surfaces you actually work in. They are
 * reference material, so they belong in the chrome rather than the nav — and
 * they render in both chromes, since a signed-in reader on /dashboard wants
 * them as much as a visitor on the landing page does.
 *
 * They open in a new tab. Reading how the score is computed is something you do
 * *while* looking at a score, and an analysis you have open is state worth
 * keeping: a same-tab hop would throw away an in-progress run's screen to show
 * a page you glance at and leave.
 */
const LINKS = [
  { href: '/methodology', label: 'Methodology' },
  { href: '/checker', label: 'Free checker' },
]

interface PublicNavLinksProps {
  /** Shorter rows, for the shell's 56px top bar. */
  compact?: boolean
}

export default function PublicNavLinks({ compact = false }: PublicNavLinksProps) {
  const height = compact ? 'min-h-[36px]' : 'min-h-[40px]'
  return (
    <>
      {LINKS.map((link) => (
        <Link
          key={link.href}
          href={link.href}
          target="_blank"
          rel="noopener noreferrer"
          // Hidden on a phone in both chromes: the row already carries a nav
          // trigger and the auth actions, and these two are the parts a narrow
          // screen can afford to lose — every page that matters links to them
          // in its own body.
          className={`hidden ${height} items-center rounded px-2 text-sm font-medium text-surface-subtle hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary sm:inline-flex`}
        >
          {link.label}
        </Link>
      ))}
    </>
  )
}
