import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import PageContainer from '@/components/shell/PageContainer'

/**
 * The analysis flow drifted to six different content widths — the running
 * screen at 768px, its own finished screen at 1152px, the sibling tabs at
 * 1024px, and two states with no container at all. The box moved under the
 * reader as a run progressed and again as they changed tabs. One component
 * owns the width now, so a screen can only opt out on purpose.
 */
describe('PageContainer', () => {
  it('centres its children at the product content width', () => {
    render(
      <PageContainer>
        <p>content</p>
      </PageContainer>,
    )

    const box = screen.getByText('content').parentElement!
    expect(box.className).toContain('mx-auto')
    expect(box.className).toContain('max-w-6xl')
  })

  it('carries the same horizontal padding at every breakpoint it defines', () => {
    render(
      <PageContainer>
        <p>content</p>
      </PageContainer>,
    )

    const box = screen.getByText('content').parentElement!
    expect(box.className).toContain('px-6')
    expect(box.className).toContain('sm:px-8')
  })

  it('takes extra classes without losing the width it exists to hold', () => {
    render(
      <PageContainer className="pb-16">
        <p>content</p>
      </PageContainer>,
    )

    const box = screen.getByText('content').parentElement!
    expect(box.className).toContain('pb-16')
    expect(box.className).toContain('max-w-6xl')
  })
})
