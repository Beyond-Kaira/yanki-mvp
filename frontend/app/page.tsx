import { LandingClosingCta, LandingHeroCta } from '@/components/LandingCta'

/**
 * The front door.
 *
 * This used to render the product shell and the analysis form, so a first-time
 * visitor's opening experience was a signed-out application with a URL box and
 * no explanation. That is a demo, not a landing page.
 *
 * Deliberately a SERVER component with no `AppShell`: the copy needs no session,
 * so it should not wait for one. Only the calls to action differ by who is
 * reading, and those are client islands that resolve on their own.
 */

const PROOF = [
  {
    title: 'Every answer, kept',
    body: 'We store the raw response behind every number. A score you cannot inspect is a score you cannot act on.',
  },
  {
    title: 'Search visibility too',
    body: 'Whether ordinary search results find you, measured next to the AI-answer score — not instead of it.',
  },
  {
    title: 'Honest gaps',
    body: 'When a check could not run, it says "not measured" rather than quietly scoring zero.',
  },
]

const STEPS = [
  { n: '1', title: 'Give us a URL', body: 'We read the site the way an answer engine would.' },
  { n: '2', title: 'We ask the engines', body: 'Real questions a buyer would type, put to live AI search.' },
  { n: '3', title: 'You see the work', body: 'A score, the evidence under it, and what to change first.' },
]

export default function LandingPage() {
  return (
    <div className="mx-auto w-full max-w-6xl px-5 py-12 sm:px-8 sm:py-16">
      <section className="max-w-3xl">
        <p className="text-sm font-medium uppercase tracking-wide text-primary">
          Generative engine optimization
        </p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-5xl">
          Find out what AI answers say about your brand
        </h1>
        <p className="mt-5 text-base leading-relaxed text-surface-subtle sm:text-lg">
          When someone asks an AI assistant to recommend a product like yours, do you
          come up? Yanki asks the engines directly, measures how often you appear, and
          keeps every raw answer so you can check the working.
        </p>

        <LandingHeroCta />
      </section>

      <section className="mt-14 grid gap-6 sm:mt-20 sm:grid-cols-3">
        {PROOF.map((item) => (
          <div
            key={item.title}
            className="rounded-lg border border-surface-border bg-surface p-5"
          >
            <h2 className="text-base font-semibold">{item.title}</h2>
            <p className="mt-2 text-sm leading-relaxed text-surface-subtle">{item.body}</p>
          </div>
        ))}
      </section>

      <section className="mt-14 sm:mt-20">
        <h2 className="text-xl font-semibold tracking-tight sm:text-2xl">How it works</h2>
        <ol className="mt-6 grid gap-6 sm:grid-cols-3">
          {STEPS.map((step) => (
            <li key={step.n} className="flex gap-4">
              <span
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary/10 text-sm font-semibold text-primary"
                aria-hidden
              >
                {step.n}
              </span>
              <div className="min-w-0">
                <h3 className="text-base font-semibold">{step.title}</h3>
                <p className="mt-1 text-sm leading-relaxed text-surface-subtle">
                  {step.body}
                </p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <LandingClosingCta />
    </div>
  )
}
