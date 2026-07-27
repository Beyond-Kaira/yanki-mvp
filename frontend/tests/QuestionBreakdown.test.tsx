import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import QuestionBreakdown from '@/components/QuestionBreakdown'
import type { QuestionGroup } from '@/lib/results'
import { axeCheck } from './a11y'

const groups: QuestionGroup[] = [
  {
    prompt: {
      id: 'p1',
      category: 'recommendation',
      text: 'Best analytics tools?',
    },
    responses: [
      {
        id: 'r1',
        engine: 'anthropic',
        model: 'mock',
        footprint: true,
        matched_snippet: 'Acme is a strong option.',
        prompt_id: 'p1',
        raw_text: 'Acme is a strong option and…',
      },
      {
        id: 'r2',
        engine: 'openai',
        model: 'mock',
        footprint: false,
        matched_snippet: null,
        prompt_id: 'p1',
        raw_text: 'Other vendors worth a look…',
      },
    ],
    mentioned: 1,
  },
] as QuestionGroup[]

describe('QuestionBreakdown', () => {
  it('shows the question, its category, and the per-engine outcome', () => {
    render(<QuestionBreakdown groups={groups} />)

    expect(screen.getByText('Best analytics tools?')).toBeInTheDocument()
    expect(screen.getByText('recommendation')).toBeInTheDocument()
    expect(screen.getByText('1/2')).toBeInTheDocument()
    // Engine ids are rendered as the product names people recognize.
    expect(screen.getByText('Claude')).toBeInTheDocument()
    expect(screen.getByText('ChatGPT')).toBeInTheDocument()
    expect(screen.queryByText('anthropic')).not.toBeInTheDocument()
  })

  it('keeps the answers collapsed until asked for', async () => {
    const user = userEvent.setup()
    render(<QuestionBreakdown groups={groups} />)

    expect(screen.queryByText(/Acme is a strong option and/)).not.toBeInTheDocument()

    const toggle = screen.getByRole('button', { name: /show answers/i })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')

    await user.click(toggle)

    expect(screen.getByText(/Acme is a strong option and/)).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /hide answers/i }),
    ).toHaveAttribute('aria-expanded', 'true')
  })

  it('has no axe violations', async () => {
    const { container } = render(
      <main>
        <QuestionBreakdown groups={groups} />
      </main>,
    )
    expect(await axeCheck(container)).toHaveNoViolations()
  })
})
