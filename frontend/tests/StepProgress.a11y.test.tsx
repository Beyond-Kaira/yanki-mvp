import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import StepProgress from '@/components/StepProgress'
import { axeCheck } from './a11y'

describe('StepProgress accessibility', () => {
  it('has no axe violations while running with an active step', async () => {
    const { container } = render(
      <main>
        <StepProgress status="running" progress={30} currentStep="prompts" />
      </main>,
    )
    // Covers the progressbar role + aria-valuenow and the aria-live status line.
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '30')
    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('has no axe violations while queued', async () => {
    const { container } = render(
      <main>
        <StepProgress status="queued" progress={0} currentStep={null} />
      </main>,
    )
    expect(await axeCheck(container)).toHaveNoViolations()
  })

  it('describes the active step under its label', () => {
    render(<StepProgress status="running" progress={30} currentStep="prompts" />)
    expect(
      screen.getByText('Generating the questions your buyers ask.'),
    ).toBeInTheDocument()
    // Only the active step carries a description.
    expect(
      screen.queryByText("Fetching and reading your site's content."),
    ).not.toBeInTheDocument()
  })

  it('shows the engine panel only during execute', async () => {
    const { container, rerender } = render(
      <main>
        <StepProgress status="running" progress={45} currentStep="execute" />
      </main>,
    )
    expect(
      screen.getByText('Asking 4 AI engines the questions your buyers ask'),
    ).toBeInTheDocument()
    for (const engine of ['Claude', 'ChatGPT', 'Gemini', 'Perplexity']) {
      expect(screen.getByText(engine)).toBeInTheDocument()
    }
    expect(await axeCheck(container)).toHaveNoViolations()

    rerender(
      <main>
        <StepProgress status="running" progress={30} currentStep="prompts" />
      </main>,
    )
    expect(screen.queryByText('Claude')).not.toBeInTheDocument()
  })

  it('hides the timer, descriptions, and engine panel when failed', () => {
    render(<StepProgress status="failed" progress={45} currentStep="execute" />)
    expect(screen.queryByText(/elapsed/)).not.toBeInTheDocument()
    expect(screen.queryByText('Claude')).not.toBeInTheDocument()
    expect(
      screen.queryByText('Running your buyer questions against each engine.'),
    ).not.toBeInTheDocument()
  })

  it('keeps the locked time expectation copy', () => {
    // docs/frontend-brandkit.md locks "a few minutes"; docs/02-mvp.md NFR-2
    // targets ~10 minutes. Anything shorter promises precision we do not have.
    render(<StepProgress status="running" progress={30} currentStep="prompts" />)
    expect(screen.getByText('This takes a few minutes.')).toBeInTheDocument()
  })

  it('marks the failed step even when a stale progress covers it', () => {
    // A re-claimed run restarts at discovery without resetting progress, so the
    // envelope can report current_step='discovery' alongside progress=80.
    render(<StepProgress status="failed" progress={80} currentStep="discovery" />)

    const steps = screen.getAllByRole('listitem')
    // Discovery is the step that died: failed, not completed.
    expect(steps[0]).toHaveTextContent('failed')
    expect(steps[0]).not.toHaveTextContent('completed')
    // Nothing after it ran on this attempt, whatever the stale number says.
    for (const step of steps.slice(1)) {
      expect(step).toHaveTextContent('waiting')
      expect(step).not.toHaveTextContent('completed')
    }
  })

  it('drops in-progress semantics on the failed screen', () => {
    const { rerender } = render(
      <StepProgress status="running" progress={45} currentStep="execute" />,
    )
    expect(screen.getByRole('progressbar')).toBeInTheDocument()

    rerender(<StepProgress status="failed" progress={45} currentStep="execute" />)
    // Polling has stopped: a live progressbar would contradict the failure.
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  })

  it('counts elapsed time from the run, not from mount', () => {
    const startedAt = new Date(Date.now() - 75_000).toISOString()
    render(
      <StepProgress
        status="running"
        progress={30}
        currentStep="prompts"
        createdAt={startedAt}
      />,
    )
    // 75s in, and past the minute rollover the plain seconds count would miss.
    expect(screen.getByText('1:15 elapsed')).toBeInTheDocument()
  })
})
