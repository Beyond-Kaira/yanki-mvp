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
})
