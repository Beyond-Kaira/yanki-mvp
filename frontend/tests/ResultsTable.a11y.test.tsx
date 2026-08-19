import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ResultsTable from '@/components/ResultsTable'
import type { AnalysisResponse, Prompt } from '@/lib/contracts'
import { axeCheck } from './a11y'
import { samplePrompt } from './analysisMocks'

const prompts: Prompt[] = [
  samplePrompt({ id: 'p1', category: 'comparison', text: 'Best CRM for small teams?' }),
  samplePrompt({ id: 'p2', category: 'recommendation', text: 'Which analytics tool should I pick?' }),
]

const responses: AnalysisResponse[] = [
  {
    id: 'r1',
    engine: 'openai',
    model: 'gpt-4o-mini',
    footprint: true,
    matched_snippet: 'Acme is a strong option for small teams.',
    prompt_id: 'p1',
    raw_text: 'Acme is a strong option for small teams and offers…',
    cost_usd: 0.0021,
  },
  {
    id: 'r2',
    engine: 'anthropic',
    model: 'claude-3-5-haiku',
    footprint: false,
    matched_snippet: null,
    prompt_id: 'p2',
    raw_text: 'There are several analytics tools worth considering…',
    cost_usd: 0.0018,
  },
]

describe('ResultsTable accessibility', () => {
  it('has no axe violations across footprint yes/no and a null snippet', async () => {
    const { container } = render(
      <main>
        <ResultsTable responses={responses} prompts={prompts} />
      </main>,
    )
    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('has no axe violations with a full-answer row expanded', async () => {
    const user = userEvent.setup()
    const { container } = render(
      <main>
        <ResultsTable responses={responses} prompts={prompts} />
      </main>,
    )
    await user.click(
      screen.getAllByRole('button', { name: /show full answer/i })[0],
    )
    expect(
      screen.getByRole('button', { name: /hide full answer/i }),
    ).toHaveAttribute('aria-expanded', 'true')
    expect(await axeCheck(container)).toHaveNoViolations()
  })
})
