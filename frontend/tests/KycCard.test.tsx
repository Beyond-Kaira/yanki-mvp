import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import KycCard from '@/components/KycCard'
import type { KYC } from '@/lib/contracts'

const fullKyc: KYC = {
  company: 'Acme Analytics',
  description: 'Acme builds analytics tools for small, fast-moving teams.',
  industry: 'Business intelligence software',
  aliases: ['Acme', 'Acme Inc'],
  products: ['Dashboards', 'Reports'],
  services: ['Onboarding', 'Support'],
  keywords: ['analytics', 'CRM'],
  locations: ['San Francisco', 'Berlin'],
  competitors: ['Globex', 'Initech'],
}

const emptyKyc: KYC = {
  company: 'Solo Co',
  description: '',
  industry: '',
  aliases: [],
  products: [],
  services: [],
  keywords: [],
  locations: [],
  competitors: [],
}

describe('KycCard', () => {
  it('renders the full profile with company, description and every labeled row', () => {
    render(
      <main>
        <KycCard kyc={fullKyc} />
      </main>,
    )

    expect(
      screen.getByRole('heading', { name: /company profile \(kyc\)/i }),
    ).toBeInTheDocument()
    expect(screen.getByText('Acme Analytics')).toBeInTheDocument()
    expect(screen.getByText(/Acme builds analytics tools/)).toBeInTheDocument()

    // Labeled text rows.
    expect(screen.getByText('Industry')).toBeInTheDocument()
    expect(screen.getByText('Business intelligence software')).toBeInTheDocument()
    expect(screen.getByText('Locations')).toBeInTheDocument()
    expect(screen.getByText('San Francisco, Berlin')).toBeInTheDocument()

    // Chip rows: labels present and individual chips rendered.
    for (const label of ['Aliases', 'Keywords', 'Products', 'Services', 'Competitors']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
    expect(screen.getByText('Acme Inc')).toBeInTheDocument()
    expect(screen.getByText('Globex')).toBeInTheDocument()

    // Chips are real list items, not a raw JSON dump.
    expect(screen.getAllByRole('listitem').length).toBeGreaterThan(0)
    expect(screen.queryByText(/"company":/)).not.toBeInTheDocument()
  })

  it('does not crash when fields are missing entirely (unvalidated free-form JSON)', () => {
    // KYC is free-form JSON with no runtime validation, so keys the type
    // declares as present may be absent at runtime. Only `company` is set here.
    const sparseKyc = { company: 'Bare Co' } as unknown as KYC

    render(
      <main>
        <KycCard kyc={sparseKyc} />
      </main>,
    )

    expect(
      screen.getByRole('heading', { name: /company profile \(kyc\)/i }),
    ).toBeInTheDocument()
    expect(screen.getByText('Bare Co')).toBeInTheDocument()
    expect(screen.queryAllByRole('listitem')).toHaveLength(0)
  })

  it('omits empty rows and renders without crashing for a partial profile', () => {
    render(
      <main>
        <KycCard kyc={emptyKyc} />
      </main>,
    )

    // The heading and company name still render.
    expect(
      screen.getByRole('heading', { name: /company profile \(kyc\)/i }),
    ).toBeInTheDocument()
    expect(screen.getByText('Solo Co')).toBeInTheDocument()

    // Empty text rows and chip rows are omitted entirely.
    for (const label of [
      'Industry',
      'Locations',
      'Aliases',
      'Keywords',
      'Products',
      'Services',
      'Competitors',
    ]) {
      expect(screen.queryByText(label)).not.toBeInTheDocument()
    }
    expect(screen.queryAllByRole('listitem')).toHaveLength(0)
  })

  it('renders the buying category and use cases when the profile carries them', () => {
    // These are the fields prompt generation is actually built from, so a user
    // can see whether we understood their business before reading the score.
    const kyc: KYC = {
      ...fullKyc,
      category: 'analytics platforms',
      use_cases: ['revenue reporting', 'churn tracking'],
    }

    render(
      <main>
        <KycCard kyc={kyc} />
      </main>,
    )

    expect(screen.getByText('Category')).toBeInTheDocument()
    expect(screen.getByText('analytics platforms')).toBeInTheDocument()
    expect(screen.getByText('Use cases')).toBeInTheDocument()
    expect(screen.getByText('churn tracking')).toBeInTheDocument()
  })

  it('omits the new rows for a profile stored before they existed', () => {
    // Rows persisted by an earlier pipeline have no such key at all.
    render(
      <main>
        <KycCard kyc={fullKyc} />
      </main>,
    )

    expect(screen.queryByText('Category')).not.toBeInTheDocument()
    expect(screen.queryByText('Use cases')).not.toBeInTheDocument()
  })
})
