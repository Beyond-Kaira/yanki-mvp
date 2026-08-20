import { describe, it, expect } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ResultsTable from '@/components/ResultsTable'
import type { AnalysisResponse, Prompt } from '@/lib/contracts'
import { samplePrompt } from './analysisMocks'

const prompts: Prompt[] = [
  samplePrompt({ id: 'p1', category: 'comparison', text: 'Best CRM for small teams?' }),
  samplePrompt({ id: 'p2', category: 'recommendation', text: 'Which analytics tool should I pick?' }),
]

const RAW_ONE =
  'Acme is a strong option for small teams and offers dashboards, reporting and onboarding support that scales.'
const RAW_TWO =
  'There are several analytics tools worth considering, including Globex and Initech, depending on your needs.'

const responses: AnalysisResponse[] = [
  {
    id: 'r1',
    engine: 'openai',
    model: 'gpt-4o-mini',
    footprint: true,
    matched_snippet: 'Acme is a strong option for small teams.',
    prompt_id: 'p1',
    raw_text: RAW_ONE,
    cost_usd: 0.0021,
  },
  {
    id: 'r2',
    engine: 'anthropic',
    model: 'claude-3-5-haiku',
    footprint: false,
    matched_snippet: null,
    prompt_id: 'p2',
    raw_text: RAW_TWO,
    cost_usd: 0.0018,
  },
]

describe('ResultsTable full-answer expansion', () => {
  it('collapses raw answers by default', () => {
    render(<ResultsTable responses={responses} prompts={prompts} />)

    expect(screen.queryByText(RAW_ONE)).not.toBeInTheDocument()
    expect(screen.queryByText(RAW_TWO)).not.toBeInTheDocument()

    const toggles = screen.getAllByRole('button', { name: /show full answer/i })
    expect(toggles).toHaveLength(2)
    for (const toggle of toggles) {
      expect(toggle).toHaveAttribute('aria-expanded', 'false')
    }
  })

  it('expands the clicked row and collapses it again', async () => {
    const user = userEvent.setup()
    render(<ResultsTable responses={responses} prompts={prompts} />)

    const toggle = screen.getAllByRole('button', { name: /show full answer/i })[0]
    await user.click(toggle)

    const expanded = screen.getByRole('button', { name: /hide full answer/i })
    expect(expanded).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText(RAW_ONE)).toBeInTheDocument()
    // Only the clicked row expanded.
    expect(screen.queryByText(RAW_TWO)).not.toBeInTheDocument()

    await user.click(expanded)
    expect(screen.queryByText(RAW_ONE)).not.toBeInTheDocument()
    expect(
      screen.getAllByRole('button', { name: /show full answer/i })[0],
    ).toHaveAttribute('aria-expanded', 'false')
  })

  it('lets multiple rows stay open at once', async () => {
    const user = userEvent.setup()
    render(<ResultsTable responses={responses} prompts={prompts} />)

    const [first, second] = screen.getAllByRole('button', {
      name: /show full answer/i,
    })
    await user.click(first)
    await user.click(second)

    expect(screen.getByText(RAW_ONE)).toBeInTheDocument()
    expect(screen.getByText(RAW_TWO)).toBeInTheDocument()
    expect(
      screen.getAllByRole('button', { name: /hide full answer/i }),
    ).toHaveLength(2)
  })

  it('shows a quiet placeholder for an empty raw answer', async () => {
    const user = userEvent.setup()
    const emptyResponses: AnalysisResponse[] = [
      { ...responses[0], raw_text: '   ' },
    ]
    render(<ResultsTable responses={emptyResponses} prompts={prompts} />)

    await user.click(screen.getByRole('button', { name: /show full answer/i }))
    expect(screen.getByText('(empty answer)')).toBeInTheDocument()
  })

  it('uses a fixed table layout so columns cannot overflow', () => {
    const { container } = render(
      <ResultsTable responses={responses} prompts={prompts} />,
    )
    const table = container.querySelector('table')
    expect(table).not.toBeNull()
    expect(table).toHaveClass('table-fixed')
  })

  it('truncates long snippets and models inside a titled span', () => {
    const longSnippet =
      'Acmelongunbrokenmonospacedsnippetstringthatwouldotherwiseblowoutitscolumnwidthonwidedesktops'
    const longModel = 'gemini-flash-lite-latest:ungrounded'
    const pathological: AnalysisResponse[] = [
      { ...responses[0], matched_snippet: longSnippet, model: longModel },
    ]
    render(<ResultsTable responses={pathological} prompts={prompts} />)

    const snippet = screen.getByText(longSnippet)
    expect(snippet).toHaveClass('truncate')
    expect(snippet).toHaveAttribute('title', longSnippet)

    const model = screen.getByText(longModel)
    expect(model).toHaveClass('truncate')
    expect(model).toHaveAttribute('title', longModel)
  })

  it('links each toggle to the answer region it controls', async () => {
    const user = userEvent.setup()
    render(<ResultsTable responses={responses} prompts={prompts} />)

    const toggle = screen.getAllByRole('button', { name: /show full answer/i })[0]
    const controlledId = toggle.getAttribute('aria-controls')
    expect(controlledId).toBeTruthy()

    await user.click(toggle)
    const region = document.getElementById(controlledId as string)
    expect(region).not.toBeNull()
    expect(within(region as HTMLElement).getByText(RAW_ONE)).toBeInTheDocument()
  })
})
