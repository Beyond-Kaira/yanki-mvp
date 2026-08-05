import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import LandingPage from '@/app/page'
import { axeCheck } from './a11y'

describe('Landing page accessibility', () => {
  it('has no axe violations', async () => {
    const { container } = render(<LandingPage />)
    expect(await axeCheck(container)).toHaveNoViolations()
  })
})
