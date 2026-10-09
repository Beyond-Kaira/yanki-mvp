import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import AnalysisProgressCard from '@/components/ai-visibility/AnalysisProgressCard'
import type { AnalysisSummary } from '@/lib/contracts'
import { axeCheck } from './a11y'

const running: AnalysisSummary = {
  id: 'active-1', url: 'https://acme.test/', status: 'running', progress: 45,
  current_step: 'execute', error: null, created_at: new Date(Date.now() - 75_000).toISOString(),
  updated_at: new Date().toISOString(), geo_score: null,
}

describe('compact analysis progress', () => {
  it('starts collapsed and opens all six steps without losing progress', async () => {
    const { container } = render(<main><AnalysisProgressCard analysis={running} /></main>)
    const toggle = screen.getByRole('button', { name: /show analysis steps/i })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('list', { name: 'Analysis steps' })).not.toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '45')
    expect(await axeCheck(container)).toHaveNoViolations()
    await userEvent.click(toggle)
    const steps = screen.getByRole('list', { name: 'Analysis steps' })
    expect(within(steps).getAllByRole('listitem')).toHaveLength(6)
    expect(within(steps).getAllByRole('listitem')[3]).toHaveAttribute('aria-current', 'step')
    expect(screen.getByText('1:15 elapsed')).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '45')
    expect(await axeCheck(container)).toHaveNoViolations()
    await userEvent.click(screen.getByRole('button', { name: /collapse analysis steps/i }))
    expect(screen.queryByRole('list', { name: 'Analysis steps' })).not.toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '45')
    expect(screen.getByRole('button', { name: /show analysis steps/i })).toHaveAttribute('aria-expanded', 'false')
    await userEvent.click(screen.getByRole('button', { name: /show analysis steps/i }))
    expect(screen.getByRole('list', { name: 'Analysis steps' })).toBeVisible()
  })

  it('offers guided review without implying measurement is still running', async () => {
    const { container } = render(<main><AnalysisProgressCard analysis={{ ...running, status: 'awaiting_review', current_step: 'prompts' }} /></main>)
    expect(screen.getByRole('link', { name: /review profile and prompts/i })).toHaveAttribute('href', '/ai-visibility?analysis=active-1')
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
    expect(screen.queryByText(/elapsed/)).not.toBeInTheDocument()
    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('marks a reclaimed running or failed step using current_step, not stale progress', async () => {
    const { rerender } = render(<AnalysisProgressCard analysis={{ ...running, progress: 80, current_step: 'discovery' }} />)
    await userEvent.click(screen.getByRole('button', { name: /show analysis steps/i }))
    let steps = within(screen.getByRole('list', { name: 'Analysis steps' })).getAllByRole('listitem')
    expect(steps[0]).toHaveTextContent('in progress')
    expect(steps.slice(1).every(step => step.textContent?.includes('waiting'))).toBe(true)
    rerender(<AnalysisProgressCard analysis={{ ...running, status: 'failed', progress: 80, current_step: 'discovery', error: 'Discovery timed out.' }} />)
    steps = within(screen.getByRole('list', { name: 'Analysis steps' })).getAllByRole('listitem')
    expect(steps[0]).toHaveTextContent('failed')
    expect(screen.getByRole('alert')).toHaveTextContent('Discovery timed out.')
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  })
})
