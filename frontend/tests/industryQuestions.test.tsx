import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import IndustryQuestionsEditor from '@/app/ai-visibility/industry-citations/IndustryQuestionsEditor'

const sample = {
  industry: 'Shoes',
  country: 'Türkiye',
  language: 'tr',
  model: 'test/model',
  cost_usd: 0,
  questions: Array.from(
    { length: 10 },
    (_, index) => 'How should I evaluate option ' + index + '?',
  ),
}

// The previous editor is retained but is no longer mounted on the industry route.
describe('retained question editor', () => {
  it('allows editing without claiming analysis execution is connected', () => {
    render(<IndustryQuestionsEditor sample={sample} editable />)
    fireEvent.change(screen.getByLabelText('Question 1'), {
      target: { value: 'Which materials are suitable for running?' },
    })
    expect(screen.getByLabelText('Question 1')).toHaveValue(
      'Which materials are suitable for running?',
    )
    fireEvent.click(screen.getByRole('button', { name: 'Add question' }))
    expect(screen.getByLabelText('Question 11')).toHaveAttribute(
      'aria-invalid',
      'true',
    )
    fireEvent.click(screen.getByRole('button', { name: 'Remove question 11' }))
    expect(screen.queryByLabelText('Question 11')).not.toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Start analysis' }),
    ).toBeDisabled()
  })
  it('renders the direct path read-only', () => {
    render(<IndustryQuestionsEditor sample={sample} editable={false} />)
    expect(
      screen.queryByRole('button', { name: 'Add question' }),
    ).not.toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Start analysis' }),
    ).toBeDisabled()
  })
})
