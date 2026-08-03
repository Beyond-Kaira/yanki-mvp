import type { KYC } from '@/lib/contracts'

interface KycCardProps {
  kyc: KYC
}

interface TextRow {
  label: string
  value: string
}

interface ChipRow {
  label: string
  items: string[]
}

// KYC is free-form JSON with no runtime validation (see lib/contracts.ts), so a
// field the type declares as present may still be missing/undefined at runtime.
// Coerce defensively so a partial profile degrades gracefully instead of
// crashing the whole result page.
function asText(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function asChips(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.filter(
    (item): item is string => typeof item === 'string' && item.trim().length > 0,
  )
}

export default function KycCard({ kyc }: KycCardProps) {
  const textRows: TextRow[] = [
    // Category leads: it is the field the prompts are actually built from, so
    // showing it is how a user can tell whether we understood their business.
    { label: 'Category', value: asText(kyc.category) },
    { label: 'Industry', value: asText(kyc.industry) },
    { label: 'Locations', value: asChips(kyc.locations).join(', ') },
  ].filter((row) => row.value.trim().length > 0)

  const chipRows: ChipRow[] = [
    { label: 'Aliases', items: asChips(kyc.aliases) },
    { label: 'Keywords', items: asChips(kyc.keywords) },
    { label: 'Use cases', items: asChips(kyc.use_cases) },
    { label: 'Products', items: asChips(kyc.products) },
    { label: 'Services', items: asChips(kyc.services) },
    { label: 'Competitors', items: asChips(kyc.competitors) },
  ].filter((row) => row.items.length > 0)

  const companyName = asText(kyc.company)
  const description = asText(kyc.description)
  const hasCompany = companyName.trim().length > 0
  const hasDescription = description.trim().length > 0
  const hasDetails = textRows.length > 0 || chipRows.length > 0

  return (
    <section className="space-y-3">
      <h2 className="text-xl font-semibold text-surface-foreground">
        Company profile (KYC)
      </h2>
      <div className="space-y-6 rounded-xl bg-ink p-6 font-mono shadow-sm">
        {hasCompany || hasDescription ? (
          <div className="space-y-2">
            {hasCompany ? (
              <p className="text-2xl font-semibold text-ink-foreground">
                {companyName}
              </p>
            ) : null}
            {hasDescription ? (
              <p className="text-sm leading-relaxed text-ink-foreground">
                {description}
              </p>
            ) : null}
          </div>
        ) : null}

        {hasDetails ? (
          <dl className="space-y-4">
            {textRows.map((row) => (
              <div
                key={row.label}
                className="flex flex-col gap-1 sm:flex-row sm:gap-3"
              >
                <dt className="w-32 shrink-0 text-xs font-medium uppercase tracking-wider text-ink-foreground">
                  {row.label}
                </dt>
                <dd className="text-sm text-ink-foreground">{row.value}</dd>
              </div>
            ))}
            {chipRows.map((row) => (
              <div key={row.label} className="flex flex-col gap-1.5">
                <dt className="text-xs font-medium uppercase tracking-wider text-ink-foreground">
                  {row.label}
                </dt>
                <dd>
                  <ul className="flex flex-wrap gap-2">
                    {row.items.map((item, index) => (
                      <li
                        key={`${item}-${index}`}
                        className="rounded-full bg-primary-soft px-2 py-0.5 text-xs font-medium text-primary-strong"
                      >
                        {item}
                      </li>
                    ))}
                  </ul>
                </dd>
              </div>
            ))}
          </dl>
        ) : null}
      </div>
    </section>
  )
}
