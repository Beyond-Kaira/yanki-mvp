import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import IntentHeatmap from '@/components/charts/IntentHeatmap'
import MentionShare from '@/components/insights/MentionShare'
import MultiLlmComparison from '@/components/insights/MultiLlmComparison'
import type { EngineInsight } from '@/lib/insights'

const engines: EngineInsight[] = [
  {
    engine: 'openai',
    mentioned: 3,
    total: 4,
    groups: [
      { group: 'discovery', mentioned: 2, total: 2 },
      { group: 'comparison', mentioned: 1, total: 1 },
      { group: 'recommendation', mentioned: 0, total: 1 },
    ],
    brandAnswers: 3,
    competitors: [
      { name: 'Globex', answers: 2 },
      { name: 'Initech', answers: 1 },
    ],
    share: 0.5,
    firstMentions: 2,
  },
  {
    engine: 'anthropic',
    mentioned: 2,
    total: 4,
    groups: [
      { group: 'discovery', mentioned: 1, total: 2 },
      { group: 'comparison', mentioned: 0, total: 1 },
      { group: 'recommendation', mentioned: 1, total: 1 },
    ],
    brandAnswers: 2,
    competitors: [{ name: 'Globex', answers: 2 }],
    share: 0.5,
    firstMentions: 1,
  },
]

describe('visibility insights', () => {
  it('reads the question count from the run', () => {
    render(<MultiLlmComparison engines={engines} />)

    expect(
      screen.getByText(
        'The same 4 questions, answered separately by each engine on the panel.',
      ),
    ).toBeInTheDocument()
  })

  it('keeps the original single-hue green heatmap', () => {
    const { container } = render(<IntentHeatmap engines={engines} />)

    expect(container.querySelector('.bg-primary')).toBeInTheDocument()
    expect(container.innerHTML).toContain('bg-primary/40')
    expect(container.querySelector('.bg-danger')).not.toBeInTheDocument()
    expect(container.querySelector('.bg-warning')).not.toBeInTheDocument()
  })

  it('shows competitor labels below mention-share bars', () => {
    render(<MentionShare brand="Yanki Demo Co" engines={engines} />)

    expect(screen.getAllByText(/Globex ·/)).toHaveLength(2)
    expect(screen.getByText(/Initech ·/)).toBeInTheDocument()
  })
})
