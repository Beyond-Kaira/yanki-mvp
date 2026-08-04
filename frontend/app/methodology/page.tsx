import type { Metadata } from 'next'
import Link from 'next/link'
// Build-time import of the GENERATED artifact (scripts/gen_methodology.py, wired
// into `make gen-types`). It is exported from the same version-stamped
// checker_prompts module the runner executes, so this page can never drift from
// what actually runs. Never hand-edit the JSON — regenerate it.
// Generated copy inside frontend/ (the Docker build context cannot reach
// ../shared); canonical artifact: shared/contracts/checker_methodology.json.
import methodology from '../../lib/checker_methodology.json'
// Engine naming lives in one module for every surface; this page asks for the
// vendor-qualified form, where naming the company is the point.
import { engineVendorLabel } from '@/lib/engines'

export const metadata: Metadata = {
  title: 'Methodology — how the Yanki AI visibility checker works',
  description:
    'The exact prompts, engines, and score formula behind the Yanki checker.',
}

const CAVEATS = [
  {
    title: 'One sample per prompt, for now',
    body: 'Each of the 12 prompts is asked once per engine today. A single answer can vary run to run, so treat the score as a directional signal, not a precise ranking. Repeat sampling is on the roadmap.',
  },
  {
    title: 'The score is binary today',
    body: 'Each answer is scored as a plain yes/no: did the brand get mentioned or not? A weighted 0–100 version — rewarding earlier, more prominent mentions — is coming. Today the headline percentage is simply the share of answers that named the brand.',
  },
  {
    title: 'We measure unprompted visibility',
    body: 'The 12 prompts ask about the category and never name your brand. We then search the answers for you. That is the whole point: we measure whether an engine brings you up on its own, not whether it can talk about you when asked.',
  },
  {
    title: 'English only',
    body: 'The checker runs in English today. Turkish is not yet supported — "no Turkish beats bad Turkish" — so a non-English brand is still asked the English category questions.',
  },
  {
    title: 'Results are cached for 24 hours',
    body: 'A brand + category checked twice within 24 hours returns the same cached result, so the score is stable across a session and we keep engine costs sane. A fresh run happens after the cache expires.',
  },
]

export default function MethodologyPage() {
  const { version, engines, prompts, score_formula } = methodology

  return (
    <main className="mx-auto max-w-4xl px-4 py-16 sm:px-8">
      <div className="space-y-12">
        <header className="space-y-4">
          <p className="text-xs font-medium uppercase tracking-wider text-primary-strong">
            Show our work
          </p>
          <h1 className="text-5xl font-semibold tracking-tight text-surface-foreground">
            How the checker works
          </h1>
          <p className="max-w-2xl text-base text-surface-subtle">
            No black box. These are the exact questions we ask the AI engines, the
            engines we ask, and how we turn their answers into your visibility
            score — the same definitions the checker runs on, published straight
            from the code.
          </p>
          <p className="text-sm font-mono text-surface-subtle">
            prompt set:{' '}
            <span className="text-surface-foreground">{version}</span>
          </p>
        </header>

        <section className="space-y-4" aria-labelledby="engines-heading">
          <h2 id="engines-heading" className="text-xl font-semibold text-surface-foreground">
            The engines we ask
          </h2>
          <p className="max-w-2xl text-sm text-surface-subtle">
            Every prompt is put to each of these four AI answer engines, so the
            score reflects the tools people actually use.
          </p>
          <ul className="grid gap-3 sm:grid-cols-2" aria-label="AI engines">
            {engines.map((engine) => (
              <li
                key={engine}
                className="rounded-lg border border-surface-border bg-white p-4 text-sm font-medium text-surface-foreground"
              >
                {engineVendorLabel(engine)}
              </li>
            ))}
          </ul>
        </section>

        <section className="space-y-4" aria-labelledby="prompts-heading">
          <h2 id="prompts-heading" className="text-xl font-semibold text-surface-foreground">
            The {prompts.length} fixed prompts
          </h2>
          <p className="max-w-2xl text-sm text-surface-subtle">
            The same {prompts.length} category questions run for every brand. The{' '}
            <span className="font-mono">category</span> term shown here (for
            example <span className="font-mono">solutions</span>,{' '}
            <span className="font-mono">worldwide</span>, or{' '}
            <span className="font-mono">the market leaders</span>) is replaced with
            your category, location, and a leading competitor when the check runs.
          </p>
          <ol className="space-y-3" aria-label="The fixed checker prompts">
            {prompts.map((prompt) => (
              <li
                key={prompt.index}
                className="flex gap-4 rounded-lg border border-surface-border bg-white p-4"
              >
                <span
                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary-soft text-xs font-medium text-primary-strong"
                  aria-hidden="true"
                >
                  {prompt.index}
                </span>
                <div className="space-y-1">
                  <p className="text-sm text-surface-foreground">{prompt.text}</p>
                  <p className="text-xs font-medium uppercase tracking-wider text-surface-subtle">
                    {prompt.category}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section className="space-y-4" aria-labelledby="formula-heading">
          <h2 id="formula-heading" className="text-xl font-semibold text-surface-foreground">
            The score
          </h2>
          <p className="max-w-2xl text-sm text-surface-subtle">
            {score_formula.description}
          </p>
          <div className="rounded-xl border border-surface-border bg-ink p-6">
            <code className="text-sm font-mono text-ink-foreground">
              score = {score_formula.expression}
            </code>
          </div>
          <p className="max-w-2xl text-sm text-surface-subtle">
            The result is a fraction from {score_formula.range}, shown as a 0–100%
            headline. If 16 of 48 answers named your brand, that is 33%.
          </p>
        </section>

        <section className="space-y-4" aria-labelledby="caveats-heading">
          <h2 id="caveats-heading" className="text-xl font-semibold text-surface-foreground">
            What this score does — and does not — tell you
          </h2>
          <div className="space-y-4">
            {CAVEATS.map((caveat) => (
              <div
                key={caveat.title}
                className="rounded-xl border border-surface-border bg-white p-6 shadow-sm"
              >
                <h3 className="text-base font-semibold text-surface-foreground">
                  {caveat.title}
                </h3>
                <p className="mt-1 text-sm text-surface-subtle">{caveat.body}</p>
              </div>
            ))}
          </div>
        </section>

        <footer className="border-t border-surface-border pt-8">
          <Link
            href="/checker"
            className="inline-flex min-h-[40px] items-center rounded text-sm font-medium text-primary hover:text-primary-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            Check your brand
          </Link>
        </footer>
      </div>
    </main>
  )
}
