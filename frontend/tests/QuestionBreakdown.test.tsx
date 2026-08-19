import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import QuestionBreakdown from '@/components/QuestionBreakdown'
import type { QuestionGroup } from '@/lib/results'
import { samplePrompt } from './analysisMocks'

// No casts: the fixtures satisfy the generated wire types in full, so a
// contract change breaks the build here instead of passing silently.
const groups: QuestionGroup[] = [
  {
    prompt: samplePrompt({
      id: 'p1',
      category: 'recommendation',
      text: 'Best analytics tools?',
    }),
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
  it('shows the question, its category, and the per-engine count collapsed', () => {
    render(<QuestionBreakdown groups={groups} engines={engines} />)

    expect(screen.getByText('Best analytics tools?')).toBeInTheDocument()
    expect(screen.getByText('recommendation')).toBeInTheDocument()
    expect(screen.getByText('1/2')).toBeInTheDocument()
    // The chip grid is the expanded content, not the collapsed row: a table
    // of N questions should cost N rows, not N rows of chips.
    expect(screen.queryByText('Claude')).not.toBeInTheDocument()
    expect(screen.queryByText('ChatGPT')).not.toBeInTheDocument()
  })

  it('reveals the per-engine outcome and evidence once expanded', async () => {
    const user = userEvent.setup()
    render(<QuestionBreakdown groups={groups} engines={engines} />)

    await user.click(screen.getByRole('button', { name: /expand/i }))

    // Engine ids are rendered as the product names people recognize. Both the
    // chip grid and the per-response rows name each engine, so this counts
    // occurrences rather than asserting a single match.
    expect(screen.getAllByText('Claude').length).toBeGreaterThan(0)
    expect(screen.getAllByText('ChatGPT').length).toBeGreaterThan(0)
    expect(screen.queryByText('anthropic')).not.toBeInTheDocument()
    // The quote is the per-response preview, visible without a second click —
    // it's the answer's own row, not something buried behind "show full
    // answer".
    expect(screen.getByText(/Acme is a strong option\./)).toBeInTheDocument()
    // openai's miss reads as a miss, not a blank: no quote to show, so the row
    // says so instead of just omitting one. The chip's sr-only label uses the
    // same words, so this counts occurrences rather than asserting one.
    expect(screen.getAllByText('did not name you').length).toBeGreaterThan(0)
  })

  it('counts against the panel, and lists an engine with nothing to show', async () => {
    const user = userEvent.setup()
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

    await user.click(screen.getByRole('button', { name: /expand/i }))

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
    // Both quotes live in the expanded section now, so this fixture holds a
    // single response — nothing here depends on telling two quotes apart.
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

    await user.click(screen.getByRole('button', { name: /expand/i }))

    // Matching on the exact quote (not a substring match) is what makes this
    // fail on the untrimmed value — the default text matcher normalizes
    // whitespace away, so a substring match would pass either way.
    expect(screen.getByText('“Acme leads the list.”')).toBeInTheDocument()
  })

  it('keeps the row collapsed until asked to expand', async () => {
    const user = userEvent.setup()
    render(<QuestionBreakdown groups={groups} engines={engines} />)

    expect(screen.queryByText('did not name you')).not.toBeInTheDocument()

    const toggle = screen.getByRole('button', { name: /expand/i })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')

    await user.click(toggle)

    // Chip label and per-response preview share this wording, hence a count.
    expect(screen.getAllByText('did not name you').length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /collapse/i })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
  })

  it('keeps the full transcript collapsed until its own toggle is asked', async () => {
    const user = userEvent.setup()
    render(<QuestionBreakdown groups={groups} engines={engines} />)

    await user.click(screen.getByRole('button', { name: /expand/i }))

    // The quote is visible at this point (previous test); the raw transcript
    // is a second, independent toggle and stays closed until asked for.
    expect(
      screen.queryByText(/Acme is a strong option and/),
    ).not.toBeInTheDocument()

    // Two responses, two "show full answer" toggles — anthropic's is first.
    const showFullAnswer = screen.getAllByRole('button', {
      name: /show full answer/i,
    })[0]
    expect(showFullAnswer).toHaveAttribute('aria-expanded', 'false')

    await user.click(showFullAnswer)

    expect(screen.getByText(/Acme is a strong option and/)).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /hide full answer/i }),
    ).toHaveAttribute('aria-expanded', 'true')
  })
})
