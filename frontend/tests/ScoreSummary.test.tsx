import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import ScoreSummary from '@/components/ScoreSummary'

describe('ScoreSummary', () => {
  it('reads the score band in plain language', () => {
    render(
      <ScoreSummary
        score={30}
        footprintCount={12}
        totalResponses={40}
        questionCount={10}
        engineCount={4}
      />,
    )

    expect(screen.getByRole('img')).toBeInTheDocument() // the gauge
    expect(
      screen.getByText(/make it into some answers, but most still leave you out/i),
    ).toBeInTheDocument()
  })

  it('reports the size of the run', () => {
    render(
      <ScoreSummary
        score={30}
        footprintCount={12}
        totalResponses={40}
        questionCount={10}
        engineCount={4}
      />,
    )

    for (const label of ['Questions', 'Engines', 'Answers', 'Mentions']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
    expect(screen.getByText('40')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
  })

  it('withholds the gauge and the verdict when nothing was answered', () => {
    render(
      <ScoreSummary
        score={0}
        footprintCount={0}
        totalResponses={0}
        questionCount={10}
        engineCount={4}
      />,
    )

    // A run with no answers is not a run that scored zero.
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(screen.queryByText(/rarely name you/i)).not.toBeInTheDocument()
    expect(screen.getByText(/no score/i)).toBeInTheDocument()
    // The counts are still facts, and stay.
    expect(screen.getByText('Questions')).toBeInTheDocument()
  })

  it('withholds the verdict when the run was never scored', () => {
    render(
      <ScoreSummary
        score={null}
        footprintCount={0}
        totalResponses={4}
        questionCount={1}
        engineCount={4}
      />,
    )

    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(screen.getByText(/no score/i)).toBeInTheDocument()
  })
})
