import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ShellStateProvider, {
  useShellState,
} from '@/components/shell/ShellStateProvider'

function RailStateProbe() {
  const { railHovered, setRailHovered } = useShellState()

  return (
    <>
      <output>{railHovered ? 'open' : 'closed'}</output>
      <button type="button" onClick={() => setRailHovered(true)}>
        Open
      </button>
      <button type="button" onClick={() => setRailHovered(false)}>
        Close
      </button>
    </>
  )
}

describe('ShellStateProvider', () => {
  it('keeps the rail open while routed shell content remounts', async () => {
    const user = userEvent.setup()
    const { rerender } = render(
      <ShellStateProvider>
        <RailStateProbe key="first-route" />
      </ShellStateProvider>,
    )

    await user.click(screen.getByRole('button', { name: 'Open' }))
    expect(screen.getByText('open')).toBeInTheDocument()

    rerender(
      <ShellStateProvider>
        <RailStateProbe key="second-route" />
      </ShellStateProvider>,
    )

    expect(screen.getByText('open')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.getByText('closed')).toBeInTheDocument()
  })
})
