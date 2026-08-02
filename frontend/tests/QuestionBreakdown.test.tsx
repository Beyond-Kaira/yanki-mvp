import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import QuestionBreakdown from '@/components/QuestionBreakdown'
import type { QuestionGroup } from '@/lib/results'

// No casts: the fixtures satisfy the generated wire types in full, so a
// contract change breaks the build here instead of passing silently.
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
        cost_usd: 0,
      },
      {
        id: 'r2',
        engine: 'openai',
        model: 'mock',
        footprint: false,
        matched_snippet: null,
        prompt_id: 'p1',
        raw_text: 'Other vendors worth a look…',
        cost_usd: 0,
      },
    ],
    mentioned: 1,
    snippet: 'Acme is a strong option.',
  },
]

const engines = ['anthropic', 'openai']

describe('QuestionBreakdown', () => {
  it('shows the question, its category, and the per-engine outcome', () => {
    render(<QuestionBreakdown groups={groups} engines={engines} />)

    expect(screen.getByText('Best analytics tools?')).toBeInTheDocument()
    expect(screen.getByText('recommendation')).toBeInTheDocument()
    expect(screen.getByText('1/2')).toBeInTheDocument()
    // Engine ids are rendered as the product names people recognize.
    expect(screen.getByText('Claude')).toBeInTheDocument()
    expect(screen.getByText('ChatGPT')).toBeInTheDocument()
    expect(screen.queryByText('anthropic')).not.toBeInTheDocument()
  })

  it('quotes the matched snippet as the evidence behind a mention', () => {
    render(<QuestionBreakdown groups={groups} engines={engines} />)

    expect(screen.getByText(/Acme is a strong option\./)).toBeInTheDocument()
  })

  it('counts against the panel, and lists an engine with nothing to show', () => {
    render(
      <QuestionBreakdown
        groups={groups}
        engines={['anthropic', 'openai', 'gemini']}
      />,
    )

    // Denominator follows the panel, not the number of answers that arrived.
    expect(screen.getByText('1/3')).toBeInTheDocument()
    // And the spoken count says so: this fixture holds two answers, so calling
    // the denominator "answers" would claim one gemini never produced.
    expect(screen.getByText('1 of 3 engines named you')).toBeInTheDocument()
    expect(screen.getByText('Gemini')).toBeInTheDocument()
    // "no answer", not "did not answer": whether the engine was asked is not
    // something the envelope reports, so the badge does not settle it.
    expect(screen.getByText('no answer')).toBeInTheDocument()
    expect(screen.queryByText('did not answer')).not.toBeInTheDocument()
  })

  it('explains every chip state the grid can render', () => {
    render(
      <QuestionBreakdown
        groups={groups}
        engines={['anthropic', 'openai', 'gemini']}
      />,
    )

    // This fixture puts all three states on screen at once: anthropic named the
    // brand, openai answered without naming it, gemini has no row. A legend
    // that covers two of them tells the reader a grid full of grey means the
    // engines never answered, when the middle state is the ordinary miss.
    expect(
      screen.getByText(/Each question goes to every engine/),
    ).toBeInTheDocument()

    // Each copy is asserted on its own element, not on the paragraph wrapping
    // both: the paragraph's textContent is the two of them concatenated, so a
    // state dropped from one still reads back from the other and the assertion
    // survives a legend that no longer says it.
    const seen = screen.getByText(/✓ named you in its answer/)
    // The marks are decoration over the words, same split as the chips: a
    // screen reader should hear the states, not "check mark, cross, dash".
    expect(seen).toHaveAttribute('aria-hidden', 'true')
    expect(seen).toHaveTextContent('answered without naming you')
    expect(seen).toHaveTextContent('no answer came back')

    const spoken = screen.getByText(/a green engine named you in its answer/)
    expect(spoken).toHaveTextContent('answered without naming you')
    expect(spoken).toHaveTextContent('no answer came back')
  })

  it('quotes the snippet without the whitespace around it', async () => {
    const user = userEvent.setup()
    // The collapsed preview keeps its own text so the two quotes stay
    // distinguishable; only the expanded one carries the padding.
    const padded: QuestionGroup[] = [
      {
        ...groups[0],
        responses: [
          {
            ...groups[0].responses[0],
            matched_snippet: '  Acme leads the list.\n',
          },
        ],
      },
    ]
    render(<QuestionBreakdown groups={padded} engines={engines} />)

    await user.click(screen.getByRole('button', { name: /show answers/i }))

    // textContent, not getByText: the default matcher normalizes whitespace
    // away, so it would pass on the untrimmed value too.
    expect(screen.getByText(/Acme leads the list/).textContent).toBe(
      '“Acme leads the list.”',
    )
  })

  it('keeps the answers collapsed until asked for', async () => {
    const user = userEvent.setup()
    render(<QuestionBreakdown groups={groups} engines={engines} />)

    expect(
      screen.queryByText(/Acme is a strong option and/),
    ).not.toBeInTheDocument()

    const toggle = screen.getByRole('button', { name: /show answers/i })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')

    await user.click(toggle)

    expect(screen.getByText(/Acme is a strong option and/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /hide answers/i })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
  })
})
