import type { Metadata } from 'next'
import Link from 'next/link'

export const metadata: Metadata = {
  title: 'Terms and conditions — Yanki',
  description: 'The terms that govern using Yanki.',
  // Nothing to index while the page has no terms on it.
  robots: { index: false, follow: true },
}

// PLACEHOLDER. The sign-up form links here because its checkbox has to point
// somewhere, and a link into a 404 is worse than a page that says where things
// stand. This deliberately contains no invented clauses: drafting terms is not
// a thing to approximate, and text that reads like an agreement while being
// nobody's agreement is worse than an empty page.
//
// TODO(legal): replace the body with the real terms, add the effective date,
// and drop the `robots` block above so the page can be indexed.
export default function TermsPage() {
  return (
    <main className="mx-auto max-w-2xl px-4 py-16 sm:px-8">
      <div className="space-y-6">
        <h1 className="text-4xl font-semibold tracking-tight text-surface-foreground">
          Terms and conditions
        </h1>

        <p className="text-base text-surface-subtle">
          These terms are not published yet. We are writing them alongside the
          accounts feature, and this page will carry the full text and its
          effective date once they are ready.
        </p>

        <p className="text-base text-surface-subtle">
          Until then there is nothing here to agree to, and nothing on this page
          is a binding agreement. If you have a question about how we handle
          your data in the meantime, the{' '}
          <Link
            href="/methodology"
            className="rounded font-medium text-primary hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            methodology page
          </Link>{' '}
          sets out exactly what the checker does with what you give it.
        </p>

        <div className="border-t border-surface-border pt-6">
          <Link
            href="/"
            className="inline-flex min-h-[40px] items-center rounded text-sm font-medium text-primary hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            Back to home
          </Link>
        </div>
      </div>
    </main>
  )
}
